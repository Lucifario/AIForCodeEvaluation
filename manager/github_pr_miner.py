import os
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional
from github import Github, GithubException, RateLimitExceededException
import requests
from tqdm import tqdm
import time

class GitHubPRMiner:
    def __init__(self, token: str, config: Dict):
        self.github = Github(token)
        self.config = config
        self.output_dir = Path(config['data']['output_base']) / 'github_prs'
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._check_rate_limit()

    def _check_rate_limit(self, min_remaining=50):
        """Helper to check rate limit and wait if necessary."""
        try:
            rate_limit_overview = self.github.get_rate_limit()
            core_rate_limit = rate_limit_overview.core

            remaining = core_rate_limit.remaining
            limit = core_rate_limit.limit
            reset_time = core_rate_limit.reset

            logging.info(f"GitHub API Rate Limit: {remaining}/{limit}")

            if remaining < min_remaining:
                now_utc = datetime.now(timezone.utc)

                if reset_time > now_utc:
                     sleep_duration = (reset_time - now_utc).total_seconds() + 10
                else:
                    sleep_duration = 60

                logging.warning(f"Rate limit low ({remaining}). Sleeping for {sleep_duration:.0f} seconds...")
                time.sleep(sleep_duration)
        except Exception as e:
            logging.error(f"Error checking rate limit: {e}. Sleeping for 60s.")
            time.sleep(60)

    def mine_repository(self, repo_name: str) -> List[Dict]:
        """Mine PRs from a single repository"""
        try:
            repo = self.github.get_repo(repo_name)
            prs_data = []
            now_utc = datetime.now(timezone.utc)
            days_ago = now_utc - timedelta(days=self.config['github']['query_params']['max_pr_age_days'])

            pulls = repo.get_pulls(
                state=self.config['github']['query_params']['state'],
                sort='updated',
                direction='desc'
            )

            logging.info(f"Mining PRs from {repo_name}...")

            limit = self.config['github']['query_params'].get('max_prs_to_fetch_per_repo', 100)
            
            for pr in tqdm(pulls[:limit], desc=f"Processing {repo_name}"):
                self._check_rate_limit()

                if pr.updated_at < days_ago:
                    continue

                if not pr.merged:
                    logging.info(f"Skipping PR #{pr.number}: Not merged.")
                    continue

                reviews = list(pr.get_reviews())
                unique_reviewers = len(set([r.user.login for r in reviews if r.user]))

                if unique_reviewers < self.config['github']['query_params']['min_reviewers']:
                    logging.info(f"Skipping PR #{pr.number}: Only {unique_reviewers} reviewers (need {self.config['github']['query_params']['min_reviewers']}).")
                    continue

                logging.info(f"Processing PR #{pr.number}: Meets criteria.")
                pr_data = self._extract_pr_data(pr, reviews, repo)
                if pr_data:
                    prs_data.append(pr_data)

            logging.info(f"Mined {len(prs_data)} PRs from {repo_name}")
            return prs_data

        except GithubException as e:
            if isinstance(e, RateLimitExceededException):
                logging.error(f"Rate limit exceeded for {repo_name}. Stopping.")
                self._check_rate_limit(min_remaining=1)
            else:
                logging.error(f"Error mining {repo_name}: {e}")
            return []

    def _extract_pr_data(self, pr, reviews, repo) -> Optional[Dict]:
        """Extract detailed PR information"""
        try:
            repo_name = repo.full_name
            
            diff_url = pr.diff_url
            diff_response = requests.get(diff_url)
            diff_content = diff_response.text if diff_response.ok else ""

            review_comments = []
            for review in reviews:
                review_comments.append({
                    'user': review.user.login if review.user else 'unknown',
                    'state': review.state,
                    'body': review.body,
                    'submitted_at': review.submitted_at.isoformat() if review.submitted_at else None
                })

            pr_comments = []
            for comment in pr.get_issue_comments():
                pr_comments.append({
                    'user': comment.user.login if comment.user else 'unknown',
                    'body': comment.body,
                    'created_at': comment.created_at.isoformat() if comment.created_at else None
                })

            files_changed = []
            for file in pr.get_files():
                files_changed.append({
                    'filename': file.filename,
                    'status': file.status,
                    'additions': file.additions,
                    'deletions': file.deletions,
                    'changes': file.changes,
                    'patch': file.patch if hasattr(file, 'patch') else None
                })

            pr_data = {
                'id': pr.number,
                'repository': repo_name,
                'title': pr.title,
                'body': pr.body,
                'state': pr.state,
                'merged': pr.merged,
                'merged_at': pr.merged_at.isoformat() if pr.merged_at else None,
                'created_at': pr.created_at.isoformat() if pr.created_at else None,
                'updated_at': pr.updated_at.isoformat() if pr.updated_at else None,
                'author': pr.user.login if pr.user else 'unknown',
                'reviewers': list(set([r.user.login for r in reviews if r.user])),
                'base_sha': pr.base.sha,
                'head_sha': pr.head.sha,
                'review_comments': review_comments,
                'pr_comments': pr_comments,
                'files_changed': files_changed,
                'diff': diff_content,
                'additions': pr.additions,
                'deletions': pr.deletions,
                'changed_files': pr.changed_files,
                'url': pr.html_url,
                'mined_at': datetime.now().isoformat()
            }
            
            pr_files_dir = self.output_dir / repo_name.replace('/', '_') / f"pr_{pr.number}_files"
            pr_files_dir.mkdir(parents=True, exist_ok=True)
            
            for file_info in pr_data['files_changed']:
                filename = file_info['filename']
                safe_filename = filename.replace('/', '_')

                if file_info['status'] != 'added':
                    try:
                        content_before = repo.get_contents(filename, ref=pr.base.sha).decoded_content.decode('utf-8')
                        with open(pr_files_dir / f"BEFORE_{safe_filename}", 'w', encoding='utf-8') as f:
                            f.write(content_before)
                    except Exception as e:
                        logging.warning(f"Could not fetch BEFORE content for {filename} in PR #{pr.number}: {e}")

                if file_info['status'] != 'removed':
                    try:
                        content_after = repo.get_contents(filename, ref=pr.head.sha).decoded_content.decode('utf-8')
                        with open(pr_files_dir / f"AFTER_{safe_filename}", 'w', encoding='utf-8') as f:
                            f.write(content_after)
                    except Exception as e:
                        logging.warning(f"Could not fetch AFTER content for {filename} in PR #{pr.number}: {e}")

            return pr_data

        except Exception as e:
            logging.error(f"Error extracting PR #{pr.number}: {e}")
            return None

    def save_pr_data(self, pr_data: Dict):
        """Save PR data to disk"""
        repo_dir = self.output_dir / pr_data['repository'].replace('/', '_')
        repo_dir.mkdir(parents=True, exist_ok=True)

        pr_file = repo_dir / f"pr_{pr_data['id']}.json"
        with open(pr_file, 'w', encoding='utf-8') as f:
            json.dump(pr_data, f, indent=2, ensure_ascii=False)

        diff_file = repo_dir / f"pr_{pr_data['id']}.diff"
        with open(diff_file, 'w', encoding='utf-8') as f:
            f.write(pr_data['diff'])

    def mine_all_repositories(self) -> int:
        """Mine all configured repositories"""
        total_prs = 0

        for repo_name in self.config['github']['repositories']:
            prs = self.mine_repository(repo_name)
            for pr_data in prs:
                self.save_pr_data(pr_data)
                total_prs += 1
        
        logging.info(f"Total PRs mined in this run: {total_prs}")
        return total_prs

def main():
    import yaml

    with open('config/config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    if 'YOUR_GITHUB_TOKEN_HERE' in config['github']['token']:
        logging.error("Please add your GitHub token to config/config.yaml")
        return

    miner = GitHubPRMiner(config['github']['token'], config)
    miner.mine_all_repositories()

if __name__ == '__main__':
    main()