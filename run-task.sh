#!/bin/bash
TASK_DIR="$HOME/agentindex/tasks"
QUEUE_DIR="$TASK_DIR/queue"
DONE_DIR="$TASK_DIR/done"
FAILED_DIR="$TASK_DIR/failed"
LOG_FILE="$TASK_DIR/task-runner.log"

TASK_FILE=$(ls -t "$QUEUE_DIR"/*.md 2>/dev/null | tail -1)

if [ -z "$TASK_FILE" ]; then
    echo "$(date): No task in queue." >> "$LOG_FILE"
    exit 0
fi

TASK_NAME=$(basename "$TASK_FILE")
echo "$(date): Starting task: $TASK_NAME" >> "$LOG_FILE"

cd "$HOME/agentindex"
claude -p "Read the task file at $TASK_FILE. Follow ALL instructions in it. When done, append a '## Result' section to the file describing what you did, what files you changed, and whether tests passed. Be thorough." --max-turns 50 2>> "$LOG_FILE"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    mv "$TASK_FILE" "$DONE_DIR/$TASK_NAME"
    echo "$(date): Task complete: $TASK_NAME" >> "$LOG_FILE"
else
    mv "$TASK_FILE" "$FAILED_DIR/$TASK_NAME"
    echo "$(date): Task FAILED: $TASK_NAME (exit code: $EXIT_CODE)" >> "$LOG_FILE"
fi
