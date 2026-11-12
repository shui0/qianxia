import hashlib
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path


def trace(stage: str, question: str, **fields):
    """Bounded local diagnostics: no question text, private history, or page body."""
    try:
        log = logging.getLogger('qianxia.search.trace')
        if not log.handlers:
            path = Path(__file__).resolve().parent / 'logs/search-stages.jsonl'
            path.parent.mkdir(parents=True, exist_ok=True)
            log.addHandler(RotatingFileHandler(path, maxBytes=262144, backupCount=2, encoding='utf8'))
            log.setLevel(logging.INFO)
            log.propagate = False
        log.info(json.dumps({'time': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                            'pid': os.getpid(), 'stage': stage,
                            'question_hash': hashlib.sha256(question.encode()).hexdigest()[:16],
                            **fields}, ensure_ascii=False))
    except OSError:
        pass
