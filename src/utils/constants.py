DATE_ALL_TIME = "all_time"
DATE_MONTH = "month"
DATE_WEEK = "week"
DATE_24_HOURS = "24_hours"


# constants used in application
SECRETS_YAML = "secrets.yaml"
WORK_PREFERENCES_YAML = "work_preferences.yaml"
PLAIN_TEXT_RESUME_YAML = "plain_text_resume.yaml"
LINKEDIN = "linkedin"

# String constants used in the application
DEBUG = "DEBUG"
INFO = "INFO"
WARNING = "WARNING"
ERROR = "ERROR"
CRITICAL = "CRITICAL"

MINIMUM_LOG_LEVEL = "MINIMUM_LOG_LEVEL"

# Constants in llm_manager.py
USAGE_METADATA = "usage_metadata"
OUTPUT_TOKENS = "output_tokens"
INPUT_TOKENS = "input_tokens"
TOTAL_TOKENS = "total_tokens"
TOKEN_USAGE = "token_usage"

MODEL = "model"
TIME = "time"
PROMPTS = "prompts"
REPLIES = "replies"
CONTENT = "content"
TOTAL_COST = "total_cost"

RESPONSE_METADATA = "response_metadata"
MODEL_NAME = "model_name"
SYSTEM_FINGERPRINT = "system_fingerprint"
FINISH_REASON = "finish_reason"
LOGPROBS = "logprobs"
ID = "id"
TEXT = "text"
PHRASE = "phrase"
QUESTION = "question"
OPTIONS = "options"
RESUME = "resume"
RESUME_SECTION = "resume_section"
JOB_DESCRIPTION = "job_description"
COMPANY = "company"
JOB_APPLICATION_PROFILE = "job_application_profile"
RESUME_EDUCATIONS = "resume_educations"
RESUME_JOBS = "resume_jobs"
RESUME_PROJECTS = "resume_projects"

PERSONAL_INFORMATION = "personal_information"
SELF_IDENTIFICATION = "self_identification"
LEGAL_AUTHORIZATION = "legal_authorization"
WORK_PREFERENCES = "work_preferences"
EDUCATION_DETAILS = "education_details"
EXPERIENCE_DETAILS = "experience_details"
PROJECTS = "projects"
AVAILABILITY = "availability"
SALARY_EXPECTATIONS = "salary_expectations"
CERTIFICATIONS = "certifications"
LANGUAGES = "languages"
INTERESTS = "interests"
COVER_LETTER = "cover_letter"

LLM_MODEL_TYPE = "llm_model_type"
LLM_API_URL = "llm_api_url"
LLM_MODEL = "llm_model"
OPENAI = "openai"
CLAUDE = "claude"
OLLAMA = "ollama"
GEMINI = "gemini"
HUGGINGFACE = "huggingface"
PERPLEXITY = "perplexity"

JOB_SELECTORS = [
    {"type": "css selector", "value": "script[data-testid='job-ldjson']", "attr": "innerHTML"},
    {"type": "css selector", "value": "div[data-testid='content']", "attr": "innerHTML"},
    {"type": "css selector", "value": "div[class='details']", "attr": "innerHTML"},
    {"type": "css selector", "value": "div[class*='details']", "attr": "innerHTML"},
    #{"type": "css selector", "value": "div[class*='details']:not([class*='mx-details-container-padding'])", "attr": "innerHTML"},
    {"type": "css selector", "value": "div[role='main']", "attr": "innerHTML"},
    {"type": "class", "value": "flex-shrink", "attr": "innerHTML"},
    {"type": "id", "value": "content", "attr": "innerHTML"},
    {"type": "tag name", "value": "body", "attr": "innerHTML"}  # fallback
]