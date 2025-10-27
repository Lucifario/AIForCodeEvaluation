SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PIPELINE_SCRIPT="$SCRIPT_DIR/run_pipeline.py"

(crontab -l 2>/dev/null; echo "0 0 * * 0 cd $SCRIPT_DIR && /usr/bin/python3 $PIPELINE_SCRIPT >> $SCRIPT_DIR/logs/cron.log 2>&1") | crontab -

echo "Cron job installed successfully!"
echo "Pipeline will run every Sunday at midnight"
echo "View cron jobs with: crontab -l"
echo "Remove cron job with: crontab -r"