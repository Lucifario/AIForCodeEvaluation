"""
PHASE 1 - AGGRESSIVE GITHUB SCALING VERSION
File: github_pr_miner_aggressive_v2.py

Improvements over original:
- NO artificial limits on PRs per repo (fetch ALL merged PRs)
- Relaxed filtering (minimum 1 reviewer instead of 2+)
- Extended date range (up to 5 years of history)
- Better caching and recovery
- Unified data format matching Defects4J structure
- Massive repository list (20+ diverse repos)
- Parallel processing with smart rate limiting
"""

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
import asyncio

class GitHubPRMinerAggressive:
    """Aggressive GitHub PR miner - NO LIMITS, MAXIMUM COLLECTION"""
    
    # Expanded repository list (20+ repos across domains)
    AGGRESSIVE_REPOS = [
        # JSON & Data Parsers
        'alibaba/fastjson', 'google/gson', 'FasterXML/jackson-databind',
        'google/protobuf', 'ecomfe/ecomfe-json-lib',
        
        # Testing & Mocking
        'mockito/mockito', 'junit-team/junit4', 'junit-team/junit5',
        'powermock/powermock', 'easymock/easymock',
        
        # HTTP & Networking
        'square/okhttp', 'square/retrofit', 'Netflix/feign',
        'apache/httpcomponents-client', 'AsyncHttpClient/async-http-client',
        
        # Apache Commons
        'apache/commons-lang', 'apache/commons-collections',
        'apache/commons-io', 'apache/commons-math',
        'apache/commons-codec',
        
        # Spring & Enterprise
        'spring-projects/spring-framework', 'spring-projects/spring-boot',
        'spring-projects/spring-security',
        
        # Utilities & Tools
        'google/guava', 'alibaba/arthas', 'google/error-prone',
        'jd-com/jd-fastjson', 'Netflix/hystrix',
        
        # Search & Indexing
        'elastic/elasticsearch', 'apache/lucene-solr',
        
        # Databases
        'mongodb/mongo-java-driver', 'apache/cassandra',
        
        # Build Tools
        'apache/maven', 'gradle/gradle',
        
        # Serialization
        'protostuff/protostuff', 'esotericsoftware/kryo'
    ]
    
    def __init__(self, token: str, config: Dict):
        self.github = Github(token)
        self.config = config
        
        self.output_dir = Path(config['data']['output_base']) / 'github_prs_aggressive'
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Statistics
        self.stats = {
            'total_repos_attempted': 0,
            'total_repos_successful': 0,
            'total_prs_found': 0,
            'total_prs_collected': 0,
            'total_prs_failed': 0,
            'by_repo': {}
        }
        
        # Cache for rate limit monitoring
        self.last_rate_check = None
        self.rate_check_interval = 60  # seconds
        
        self._verify_connection()
    
    def _verify_connection(self):
        """Verify GitHub connection"""
        try:
            user = self.github.get_user()
            logging.info(f"✓ Connected to GitHub as: {user.login}")
        except Exception as e:
            logging.error(f"GitHub connection failed: {e}")
            raise
    
    def _check_rate_limit_smart(self):
        """Smart rate limit checking"""
        now = time.time()
        
        # Only check periodically
        if self.last_rate_check and (now - self.last_rate_check) < self.rate_check_interval:
            return True
        
        self.last_rate_check = now
        
        try:
            rate_limit = self.github.get_rate_limit()
            remaining = rate_limit.core.remaining
            limit = rate_limit.core.limit
            reset_time = rate_limit.core.reset
            
            logging.debug(f"Rate Limit: {remaining}/{limit}")
            
            if remaining < 100:
                now_utc = datetime.now(timezone.utc)
                if reset_time > now_utc:
                    sleep_duration = (reset_time - now_utc).total_seconds() + 5
                    logging.warning(f"Rate limit low ({remaining}). Waiting {sleep_duration:.0f}s...")
                    time.sleep(sleep_duration)
                else:
                    time.sleep(60)
            
            return True
        
        except Exception as e:
            logging.warning(f"Rate limit check failed: {e}")
            time.sleep(10)
            return False
    
    def mine_repository(self, repo_name: str) -> List[Dict]:
        """Mine ALL merged PRs from repository (no limit)"""
        
        self.stats['total_repos_attempted'] += 1
        prs_data = []
        
        try:
            self._check_rate_limit_smart()
            repo = self.github.get_repo(repo_name)
            
            logging.info(f"\n{'='*50}")
            logging.info(f"Mining: {repo_name}")
            logging.info(f"Stars: {repo.stargazers_count}, Forks: {repo.forks_count}")
            
            # Extended date range - up to 5 years
            now_utc = datetime.now(timezone.utc)
            days_ago = self.config['github']['query_params'].get('max_pr_age_days', 1825)  # ~5 years
            start_date = now_utc - timedelta(days=days_ago)
            
            # Get merged PRs (NO LIMIT on iteration)
            pulls = repo.get_pulls(
                state='closed',
                sort='updated',
                direction='desc'
            )
            
            pr_count_all = 0
            pr_count_collected = 0
            pr_count_skipped = 0
            
            for pr in pulls:
                self._check_rate_limit_smart()
                
                # Date filtering
                if pr.updated_at.replace(tzinfo=timezone.utc) < start_date:
                    logging.debug(f"Reached old PRs (cutoff: {start_date}). Stopping repo scan.")
                    break
                
                # Must be merged
                if not pr.merged:
                    pr_count_skipped += 1
                    continue
                
                pr_count_all += 1
                
                # Relaxed filtering - minimum 1 reviewer
                reviews = list(pr.get_reviews())
                unique_reviewers = len(set([r.user.login for r in reviews if r.user]))
                
                min_reviewers = self.config['github']['query_params'].get('min_reviewers', 1)
                if unique_reviewers < min_reviewers:
                    pr_count_skipped += 1
                    continue
                
                # Extract and store PR data
                try:
                    pr_data = self._extract_pr_data(pr, reviews, repo)
                    if pr_data:
                        prs_data.append(pr_data)
                        pr_count_collected += 1
                except Exception as e:
                    logging.debug(f"Error extracting PR #{pr.number}: {e}")
                    self.stats['total_prs_failed'] += 1
            
            self.stats['total_repos_successful'] += 1
            self.stats['total_prs_found'] += pr_count_all
            self.stats['total_prs_collected'] += pr_count_collected
            self.stats['by_repo'][repo_name] = {
                'total_found': pr_count_all,
                'collected': pr_count_collected,
                'skipped': pr_count_skipped
            }
            
            logging.info(f"✓ Mined {pr_count_collected} PRs (found: {pr_count_all}, skipped: {pr_count_skipped})")
        
        except GithubException as e:
            logging.error(f"GitHub error mining {repo_name}: {e}")
            self.stats['by_repo'][repo_name] = {'error': str(e)}
        
        except Exception as e:
            logging.error(f"Unexpected error mining {repo_name}: {e}")
            self.stats['by_repo'][repo_name] = {'error': str(e)}
        
        return prs_data
    
    def _extract_pr_data(self, pr, reviews, repo) -> Optional[Dict]:
        """Extract PR data into unified format"""
        try:
            repo_name = repo.full_name
            
            # Get diff
            diff_url = pr.diff_url
            diff_response = requests.get(diff_url, timeout=30)
            diff_content = diff_response.text if diff_response.ok else ""
            
            # Extract review comments
            review_comments = []
            for review in reviews:
                review_comments.append({
                    'user': review.user.login if review.user else 'unknown',
                    'state': review.state,
                    'body': review.body or '',
                    'submitted_at': review.submitted_at.isoformat() if review.submitted_at else None
                })
            
            # Extract PR comments
            pr_comments = []
            for comment in pr.get_issue_comments():
                pr_comments.append({
                    'user': comment.user.login if comment.user else 'unknown',
                    'body': comment.body or '',
                    'created_at': comment.created_at.isoformat() if comment.created_at else None
                })
            
            # Extract file changes
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
            
            # Extract BEFORE/AFTER code for each file
            pr_files_dir = self.output_dir / repo_name.replace('/', '_') / f"pr_{pr.number}_files"
            pr_files_dir.mkdir(parents=True, exist_ok=True)
            
            files_extracted = 0
            
            for file_info in files_changed:
                filename = file_info['filename']
                safe_filename = filename.replace('/', '_')
                
                # BEFORE version
                if file_info['status'] != 'added':
                    try:
                        content_before = repo.get_contents(
                            filename, 
                            ref=pr.base.sha
                        ).decoded_content.decode('utf-8', errors='ignore')
                        
                        with open(pr_files_dir / f"BEFORE_{safe_filename}", 'w', encoding='utf-8') as f:
                            f.write(content_before)
                        
                        files_extracted += 1
                    except Exception as e:
                        logging.debug(f"Could not fetch BEFORE: {filename}")
                
                # AFTER version
                if file_info['status'] != 'removed':
                    try:
                        content_after = repo.get_contents(
                            filename, 
                            ref=pr.head.sha
                        ).decoded_content.decode('utf-8', errors='ignore')
                        
                        with open(pr_files_dir / f"AFTER_{safe_filename}", 'w', encoding='utf-8') as f:
                            f.write(content_after)
                        
                        files_extracted += 1
                    except Exception as e:
                        logging.debug(f"Could not fetch AFTER: {filename}")
            
            # Unified data structure (matches Defects4J format)
            pr_data = {
                'id': f"github_{repo_name.replace('/', '_')}_{pr.number}",
                'source': 'github',
                'repository': repo_name,
                'pr_number': pr.number,
                'title': pr.title or '',
                'body': pr.body or '',
                'state': pr.state,
                'merged': pr.merged,
                'merged_at': pr.merged_at.isoformat() if pr.merged_at else None,
                'created_at': pr.created_at.isoformat() if pr.created_at else None,
                'updated_at': pr.updated_at.isoformat() if pr.updated_at else None,
                'author': pr.user.login if pr.user else 'unknown',
                'reviewers': list(set([r.user.login for r in reviews if r.user])),
                'base_sha': pr.base.sha,
                'head_sha': pr.head.sha,
                'BEFORE': {
                    'ref': pr.base.sha,
                    'branch': pr.base.ref,
                    'metadata': {
                        'files_changed_count': pr.changed_files,
                        'additions': pr.additions,
                        'deletions': pr.deletions
                    }
                },
                'AFTER': {
                    'ref': pr.head.sha,
                    'branch': pr.head.ref,
                    'metadata': {
                        'files_changed_count': pr.changed_files,
                        'additions': pr.additions,
                        'deletions': pr.deletions
                    }
                },
                'HUMAN_REVIEW': {
                    'review_comments': review_comments,
                    'pr_comments': pr_comments,
                    'review_count': len(reviews),
                    'unique_reviewers': len(set([r.user.login for r in reviews if r.user]))
                },
                'files': {
                    'directory': str(pr_files_dir),
                    'extracted_count': files_extracted,
                    'total_files': len(files_changed),
                    'files_metadata': files_changed
                },
                'diff': diff_content[:50000],  # Limit diff size
                'processed_at': datetime.now().isoformat(),
                'language': 'java'  # Most repos are Java
            }
            
            return pr_data
        
        except Exception as e:
            logging.error(f"Error extracting PR data: {e}")
            return None
    
    def mine_all_repositories(self) -> List[Dict]:
        """Mine all repositories in aggressive list"""
        logging.info("\n" + "="*60)
        logging.info("AGGRESSIVE GITHUB PR COLLECTION - MAXIMUM SCALE")
        logging.info(f"Attempting {len(self.AGGRESSIVE_REPOS)} repositories")
        logging.info("="*60 + "\n")
        
        all_prs = []
        
        for repo_name in self.AGGRESSIVE_REPOS:
            try:
                prs = self.mine_repository(repo_name)
                all_prs.extend(prs)
                
                # Save per-repo results
                repo_output = self.output_dir / f"github_prs_{repo_name.replace('/', '_')}.json"
                with open(repo_output, 'w') as f:
                    json.dump(prs, f, indent=2)
            
            except Exception as e:
                logging.error(f"Fatal error with {repo_name}: {e}")
                continue
        
        # Save unified dataset
        output_file = self.output_dir / "github_prs_all_samples.json"
        with open(output_file, 'w') as f:
            json.dump(all_prs, f, indent=2)
        
        # Save statistics
        stats_file = self.output_dir / "github_collection_stats.json"
        with open(stats_file, 'w') as f:
            json.dump(self.stats, f, indent=2)
        
        logging.info("\n" + "="*60)
        logging.info("COLLECTION COMPLETE")
        logging.info(f"Repos Attempted: {self.stats['total_repos_attempted']}")
        logging.info(f"Repos Successful: {self.stats['total_repos_successful']}")
        logging.info(f"Total PRs Found: {self.stats['total_prs_found']}")
        logging.info(f"Total PRs Collected: {self.stats['total_prs_collected']}")
        logging.info(f"Total PRs Failed: {self.stats['total_prs_failed']}")
        logging.info(f"Output: {output_file}")
        logging.info("="*60 + "\n")
        
        return all_prs


def main():
    import yaml
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('github_aggressive_collection.log'),
            logging.StreamHandler()
        ]
    )
    
    # Load config
    with open('config/config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Get token
    token = config.get('github', {}).get('token')
    if not token or 'YOUR_GITHUB_TOKEN' in token:
        logging.error("Please set GitHub token in config.yaml")
        return
    
    # Run aggressive collection
    miner = GitHubPRMinerAggressive(token, config)
    all_prs = miner.mine_all_repositories()
    
    print(f"\n✓ GITHUB: Collected {len(all_prs)} total PR samples")


if __name__ == '__main__':
    main()
