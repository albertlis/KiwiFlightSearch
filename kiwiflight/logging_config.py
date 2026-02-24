import logging
import sys


class _ColoredFormatter(logging.Formatter):
    _COLORS = {
        'DEBUG': '\033[36m',
        'INFO': '\033[32m',
        'WARNING': '\033[33m',
        'ERROR': '\033[31m',
        'CRITICAL': '\033[35m',
    }
    _RESET = '\033[0m'
    _BOLD = '\033[1m'

    def format(self, record: logging.LogRecord) -> str:
        color = self._COLORS.get(record.levelname, '')
        if color:
            record.levelname = f"{color}{self._BOLD}{record.levelname}{self._RESET}"
        return super().format(record)


def setup_logging(level: int | str = logging.INFO) -> None:
    """Setup simple console logging with colors, function names and line numbers."""
    if isinstance(level, str):
        level = getattr(logging, level.upper())

    log_format = '%(asctime)s [%(levelname)s] %(name)s %(funcName)s():%(lineno)d - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = (
        _ColoredFormatter(log_format, datefmt=date_format)
        if sys.stdout.isatty()
        else logging.Formatter(log_format, datefmt=date_format)
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    logging.getLogger('urllib3').setLevel(logging.WARNING)

