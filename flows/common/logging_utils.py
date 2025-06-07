import logging
import sys
import os 

def setup_logger(logger_name, level_str=None):
    """
    Sets up a logger with a specified name and level.
    """
    if level_str is None:
        level_str = os.getenv("LOG_LEVEL", "INFO").upper() # Get from env as config might not be fully ready

    log_level = logging.getLevelName(level_str)
    
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level) 
    
    # Check if handlers are already attached to this specific logger to avoid duplication
    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # Console Handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(log_level) # Set level for the handler too
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
        # Prevent messages from propagating to the root logger if you've configured this one
        logger.propagate = False 
            
    return logger