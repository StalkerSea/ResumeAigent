# In this file, you can set the configurations of the app.

from src.utils.constants import DEBUG, ERROR, LLM_MODEL, OPENAI

#config related to logging must have prefix LOG_
LOG_LEVEL = 'ERROR'
LOG_SELENIUM_LEVEL = ERROR
LOG_TO_FILE = False
LOG_TO_CONSOLE = False

MINIMUM_WAIT_TIME_IN_SECONDS = 60

JOB_APPLICATIONS_DIR = "job_applications"
JOB_SUITABILITY_SCORE = 7

JOB_MAX_APPLICATIONS = 50
JOB_MIN_APPLICATIONS = 1

# LLM_MODEL_TYPE = 'gemini'
LLM_MODEL_TYPE = 'ollama'
# LLM_MODEL = 'gemini-2.0-flash-exp'
# LLM_MODEL = 'gemini-1.5-flash'
LLM_MODEL = 'olmo2:13b'
# Only required for OLLAMA models
LLM_API_URL = '127.0.0.1:11434'
