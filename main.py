import base64
import random
import sys
import time
from pathlib import Path
import traceback
from typing import List, Tuple, Dict
import inquirer
import yaml
from selenium import webdriver
import re
from src.libs.resume_and_cover_builder.resume_facade import ResumeFacade
from src.libs.resume_and_cover_builder.resume_generator import ResumeGenerator
from src.resume_builder.manager_facade import FacadeManager
from src.resume_builder.style_manager import StyleManager
from src.resume_schemas.resume import Resume
from src.job_portals.base_job_portal import get_job_portal
import undetected_chromedriver as uc
from selenium.common.exceptions import WebDriverException
from src.job.application_profile import JobApplicationProfile
from src.app_logging import logger
from src.utils.constants import (
    POPULAR_BLUE_PORTAL, 
    PLAIN_TEXT_RESUME_YAML, 
    SECRETS_YAML, 
    WORK_PREFERENCES_YAML
)
from src.job_portal_handler.bot_facade import HelperFacade
from src.job_portal_handler.job_manager import JobManager
from src.job_portal_handler.llm.llm_manager import GPTAnswerer


class ConfigError(Exception):
    """Custom exception for configuration-related errors."""
    pass


class ConfigValidator:
    """Validates configuration and secrets YAML files."""

    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    REQUIRED_CONFIG_KEYS = {
        "remote": bool,
        "experience_level": dict,
        "job_types": dict,
        "date": dict,
        "positions": list,
        "locations": list,
        "location_blacklist": list,
        "distance": int,
        "company_blacklist": list,
        "title_blacklist": list,
    }
    EXPERIENCE_LEVELS = [
        "internship",
        "entry",
        "associate",
        "mid_senior_level",
        "director",
        "executive",
    ]
    JOB_TYPES = [
        "full_time",
        "contract",
        "part_time",
        "temporary",
        "internship",
        "other",
        "volunteer",
    ]
    DATE_FILTERS = ["all_time", "month", "week", "24_hours"]
    APPROVED_DISTANCES = {0, 5, 10, 25, 50, 100}

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate the format of an email address."""
        return bool(ConfigValidator.EMAIL_REGEX.match(email))

    @staticmethod
    def load_yaml(yaml_path: Path) -> dict:
        """Load and parse a YAML file."""
        try:
            with open(yaml_path, "r") as stream:
                return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Error reading YAML file {yaml_path}: {exc}")
        except FileNotFoundError:
            raise ConfigError(f"YAML file not found: {yaml_path}")

    @classmethod
    def validate_config(cls, config_yaml_path: Path) -> dict:
        """Validate the main configuration YAML file."""
        parameters = cls.load_yaml(config_yaml_path)
        # Check for required keys and their types
        for key, expected_type in cls.REQUIRED_CONFIG_KEYS.items():
            if key not in parameters:
                if key in ["company_blacklist", "title_blacklist", "location_blacklist"]:
                    parameters[key] = []
                else:
                    raise ConfigError(f"Missing required key '{key}' in {config_yaml_path}")
            elif not isinstance(parameters[key], expected_type):
                if key in ["company_blacklist", "title_blacklist", "location_blacklist"] and parameters[key] is None:
                    parameters[key] = []
                else:
                    raise ConfigError(
                        f"Invalid type for key '{key}' in {config_yaml_path}. Expected {expected_type.__name__}."
                    )
        cls._validate_experience_levels(parameters["experience_level"], config_yaml_path)
        cls._validate_job_types(parameters["job_types"], config_yaml_path)
        cls._validate_date_filters(parameters["date"], config_yaml_path)
        cls._validate_list_of_strings(parameters, ["positions", "locations"], config_yaml_path)
        cls._validate_distance(parameters["distance"], config_yaml_path)
        cls._validate_blacklists(parameters, config_yaml_path)
        return parameters

    @classmethod
    def _validate_experience_levels(cls, experience_levels: dict, config_path: Path):
        """Ensure experience levels are booleans."""
        for level in cls.EXPERIENCE_LEVELS:
            if not isinstance(experience_levels.get(level), bool):
                raise ConfigError(
                    f"Experience level '{level}' must be a boolean in {config_path}"
                )

    @classmethod
    def _validate_job_types(cls, job_types: dict, config_path: Path):
        """Ensure job types are booleans."""
        for job_type in cls.JOB_TYPES:
            if not isinstance(job_types.get(job_type), bool):
                raise ConfigError(
                    f"Job type '{job_type}' must be a boolean in {config_path}"
                )

    @classmethod
    def _validate_date_filters(cls, date_filters: dict, config_path: Path):
        """Ensure date filters are booleans."""
        for date_filter in cls.DATE_FILTERS:
            if not isinstance(date_filters.get(date_filter), bool):
                raise ConfigError(
                    f"Date filter '{date_filter}' must be a boolean in {config_path}"
                )

    @classmethod
    def _validate_list_of_strings(cls, parameters: dict, keys: list, config_path: Path):
        """Ensure specified keys are lists of strings."""
        for key in keys:
            if not all(isinstance(item, str) for item in parameters[key]):
                raise ConfigError(
                    f"'{key}' must be a list of strings in {config_path}"
                )

    @classmethod
    def _validate_distance(cls, distance: int, config_path: Path):
        """Validate the distance value."""
        if distance not in cls.APPROVED_DISTANCES:
            raise ConfigError(
                f"Invalid distance value '{distance}' in {config_path}. Must be one of: {cls.APPROVED_DISTANCES}"
            )

    @classmethod
    def _validate_blacklists(cls, parameters: dict, config_path: Path):
        """Ensure blacklists are lists."""
        for blacklist in ["company_blacklist", "title_blacklist", "location_blacklist"]:
            if not isinstance(parameters.get(blacklist), list):
                raise ConfigError(
                    f"'{blacklist}' must be a list in {config_path}"
                )
            if parameters[blacklist] is None:
                parameters[blacklist] = []

    @staticmethod
    def validate_secrets(secrets_yaml_path: Path) -> str:
        """Validate the secrets YAML file and retrieve the LLM API key."""
        secrets = ConfigValidator.load_yaml(secrets_yaml_path)
        mandatory_secrets = ["llm_api_key"]

        for secret in mandatory_secrets:
            if secret not in secrets:
                raise ConfigError(f"Missing secret '{secret}' in {secrets_yaml_path}")

            if not secrets[secret]:
                raise ConfigError(f"Secret '{secret}' cannot be empty in {secrets_yaml_path}")

        return secrets["llm_api_key"]


class FileManager:
    """Handles file system operations and validations."""

    REQUIRED_FILES = [SECRETS_YAML, WORK_PREFERENCES_YAML, PLAIN_TEXT_RESUME_YAML]

    @staticmethod
    def validate_data_folder(app_data_folder: Path) -> Tuple[Path, Path, Path, Path]:
        """Validate the existence of the data folder and required files."""
        if not app_data_folder.is_dir():
            raise FileNotFoundError(f"Data folder not found: {app_data_folder}")

        missing_files = [file for file in FileManager.REQUIRED_FILES if not (app_data_folder / file).exists()]
        if missing_files:
            raise FileNotFoundError(f"Missing files in data folder: {', '.join(missing_files)}")

        output_folder = app_data_folder / "output"
        output_folder.mkdir(exist_ok=True)

        return (
            app_data_folder / SECRETS_YAML,
            app_data_folder / WORK_PREFERENCES_YAML,
            app_data_folder / PLAIN_TEXT_RESUME_YAML,
            output_folder,
        )

    @staticmethod
    def get_uploads(plain_text_resume_file: Path) -> Dict[str, Path]:
        """Convert resume file paths to a dictionary."""
        if not plain_text_resume_file.exists():
            raise FileNotFoundError(f"Plain text resume file not found: {plain_text_resume_file}")

        uploads = {"plainTextResume": plain_text_resume_file}

        return uploads


def init_uc_browser() -> webdriver.Chrome:
    try:
        from src.utils.anti_detection import UserAgentRotator
        ua_rotator = UserAgentRotator()
        random_ua = ua_rotator.get_random_agent()
        
        options = uc.ChromeOptions()
        
        # Create user data directory if it doesn't exist
        #user_data_dir = Path.home() / ".config" / "aihawk" / "chrome_data"
        user_data_dir = Path(".config/autojobaigent/chrome_data")
        user_data_dir.mkdir(parents=True, exist_ok=True)
        
        options.add_argument(f'--user-data-dir={user_data_dir}')
        options.add_argument('--profile-directory=Default')
        #options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--no-first-run')
        options.add_argument('--no-service-autorun')
        options.add_argument('--password-store=basic')
        options.binary_location = "/Applications/Chromium.app/Contents/MacOS/Chromium"
        
        # Set a random user agent
        options.add_argument(f'--user-agent={random_ua}')
        
        # Add some noise to browser fingerprint
        width = random.randint(1024, 1920)
        height = random.randint(800, 1080)
        options.add_argument(f'--window-size={width},{height}')
        
        # Disable automation flags
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-features=IsolateOrigins,site-per-process')

        # Add canvas fingerprint protection
        options.add_argument("--disable-features=CanvasImageSmoothing")
        
        
        driver = uc.Chrome(options=options)
        
        # Execute CDP commands to prevent detection
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Set random WebGL settings to prevent fingerprinting
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
            (function() {
                // Modify WebGL behavior to add noise
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    // Add slight randomization to certain parameters
                    if (parameter === 37445) {
                        return 'Intel Inc.' + (Math.random() < 0.1 ? ' ' : '');
                    }
                    if (parameter === 37446) {
                        return 'Intel' + (Math.random() < 0.1 ? ' HD Graphics' : ' Iris Pro Graphics');
                    }
                    return getParameter.apply(this, arguments);
                };
            })();
            '''
        })
        return driver
    except Exception as e:
        logger.error(f"Browser initialization failed: {str(e)}")
        raise RuntimeError(f"Failed to initialize browser: {str(e)}")


def create_and_run_bot(parameters, llm_api_key):
    try:
        style_manager = StyleManager()
        resume_generator = ResumeGenerator()
        with open(
            parameters["uploads"]["plainTextResume"], "r", encoding="utf-8"
        ) as file:
            plain_text_resume = file.read()
        resume_object = Resume(plain_text_resume)
        resume_generator_manager = FacadeManager(
            llm_api_key,
            style_manager,
            resume_generator,
            resume_object,
            Path("data_folder/output"),
        )

        # Run the resume generator manager's functions to make a new resume for each job
        resume_generator_manager.choose_style()
        job_application_profile_object = JobApplicationProfile(plain_text_resume)

        browser = init_uc_browser()
        job_portal = get_job_portal(
            driver=browser, portal_name=POPULAR_BLUE_PORTAL, parameters=parameters
        )
        login_component = job_portal.authenticator
        apply_component = JobManager(job_portal)
        gpt_answerer_component = GPTAnswerer(parameters, llm_api_key)
        bot = HelperFacade(login_component, apply_component)
        bot.set_job_application_profile_and_resume(
            job_application_profile_object, resume_object
        )
        bot.set_gpt_answerer_and_resume_generator(
            gpt_answerer_component, resume_generator_manager
        )
        bot.set_parameters(parameters, resume_object)
        bot.start_login()
        logger.info("Collecting suitable jobs")
        bot.start_apply()
    except WebDriverException as e:
        logger.error(f"WebDriver error occurred: {e}")
    except Exception as e:
        raise RuntimeError(f"Error running the bot: {str(e)}")


def create_cover_letter(parameters: dict, llm_api_key: str):
    """
    Logic to create a CV.
    """
    try:
        logger.info("Generating a CV based on provided parameters.")

        # Carica il resume in testo semplice
        with open(parameters["uploads"]["plainTextResume"], "r", encoding="utf-8") as file:
            plain_text_resume = file.read()

        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning("No styles available. Proceeding without style selection.")
        else:
            # Present style choices to the user
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for style_name, (file_name, author_link) in available_styles.items():
                    if selected_choice.startswith(style_name):
                        style_manager.set_selected_style(style_name)
                        logger.info(f"Selected style: {style_name}")
                        break
            else:
                logger.warning("No style selected. Proceeding with default style.")
        questions = [
            inquirer.Text('job_url', message="Please enter the URL of the job description")
        ]
        answers = inquirer.prompt(questions)
        job_url = answers.get('job_url')
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)
        driver = init_uc_browser()
        resume_generator.set_resume_object(resume_object)
        
        # Create the ResumeFacade
        resume_facade = ResumeFacade(            
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path("data_folder/output"),
        )
        
        # Initialize the Resume Generator
        resume_facade.set_driver(driver)
        resume_facade.link_to_job(job_url)
        result_base64, suggested_name = resume_facade.util_create_cover_letter()         

        # Decodifica Base64 in dati binari
        try:
            pdf_data = base64.b64decode(result_base64)
        except base64.binascii.Error as e:
            logger.error("Error decoding Base64: %s", e)
            raise

        # Define the path to the output folder using `suggested_name`. Maybe include the current date?
        output_dir = Path(parameters["outputFileDirectory"]) / suggested_name
        # / {datetime.now().strftime('%Y-%m-%d')}

        # Crea la cartella se non esiste
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cartella di output creata o già esistente: {output_dir}")
        except IOError as e:
            logger.error("Error creating output directory: %s", e)
            raise
        
        output_path = output_dir / "cover_letter.pdf"
        try:
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            logger.info(f"CV salvato in: {output_path}")
        except IOError as e:
            logger.error("Error writing file: %s", e)
            raise
    except Exception as e:
        logger.exception(f"An error occurred while creating the CV: {e}")
        raise


def create_resume_pdf_tailored(parameters: dict, llm_api_key: str):
    """
    Logic to create a CV.
    """
    try:
        logger.info("Generating a CV based on provided parameters.")

        # Carica il resume in testo semplice
        with open(parameters["uploads"]["plainTextResume"], "r", encoding="utf-8") as file:
            plain_text_resume = file.read()

        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning("No styles available. Proceeding without style selection.")
        else:
            # Present style choices to the user
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for style_name in available_styles.items():
                    if selected_choice.startswith(style_name[0]):
                        style_manager.set_selected_style(style_name[0])
                        logger.info(f"Selected style: {style_name[0]}")
                        break
            else:
                logger.warning("No style selected. Proceeding with default style.")
        questions = [inquirer.Text('job_url', message="Please enter the URL of the job description")]
        answers = inquirer.prompt(questions)
        try: 
            job_url = answers.get('job_url')
        except:
            logger.error("No job URL provided, exiting...")
            quit()
        
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)
        driver = init_uc_browser()
        
        resume_generator.set_resume_object(resume_object)
        resume_facade = ResumeFacade(            
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path("data_folder/output"),
        )
        resume_facade.set_driver(driver)
        resume_facade.link_to_job(job_url)

        # TODO: This doesn't work, fix!
        return
        #result_base64, suggested_name = create_resume_pdf_tailored()

        # Decodifica Base64 in dati binari
        try:
            pdf_data = base64.b64decode(result_base64)
        except base64.binascii.Error as e:
            logger.error("Error decoding Base64: %s", e)
            raise

        # Definisci il percorso della cartella di output utilizzando `suggested_name`
        output_dir = Path(parameters["outputFileDirectory"]) / suggested_name

        # Crea la cartella se non esiste
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cartella di output creata o già esistente: {output_dir}")
        except IOError as e:
            logger.error("Error creating output directory: %s", e)
            raise
        
        output_path = output_dir / "resume.pdf"
        try:
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            logger.info(f"CV salvato in: {output_path}")
        except IOError as e:
            logger.error("Error writing file: %s", e)
            raise
    except Exception as e:
        logger.exception(f"An error occurred while creating the CV: {e}")
        raise


def create_resume_pdf(parameters: dict, llm_api_key: str):
    """
    Logic to create a CV.
    """
    try:
        logger.info("Generating a CV based on provided parameters.")

        # Load the plain text resume
        with open(parameters["uploads"]["plainTextResume"], "r", encoding="utf-8") as file:
            plain_text_resume = file.read()

        # Initialize StyleManager
        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning("No styles available. Proceeding without style selection.")
        else:
            # Present style choices to the user
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for style_name, (file_name, author_link) in available_styles.items():
                    if selected_choice.startswith(style_name):
                        style_manager.set_selected_style(style_name)
                        logger.info(f"Selected style: {style_name}")
                        break
            else:
                logger.warning("No style selected. Proceeding with default style.")

        # Initialize the Resume Generator
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)

        # Making it headless, as it just generates the html and converts it to PDF
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        driver = init_uc_browser(options=options)

        resume_generator.set_resume_object(resume_object)

        # Create the ResumeFacade
        resume_facade = ResumeFacade(
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path("data_folder/output"),
        )
        resume_facade.set_driver(driver)
        result_base64 = resume_facade.create_resume_pdf()

        # Decode Base64 to binary data
        try:
            pdf_data = base64.b64decode(result_base64)
        except base64.binascii.Error as e:
            logger.error("Error decoding Base64: %s", e)
            raise

        # Define the output directory using `suggested_name`
        output_dir = Path(parameters["outputFileDirectory"])

        # Write the PDF file
        output_path = output_dir / "resume_base.pdf"
        try:
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            logger.info(f"Resume saved at: {output_path}")
        except IOError as e:
            logger.error("Error writing file: %s", e)
            raise
    except Exception as e:
        logger.exception(f"An error occurred while creating the CV: {e}")
        raise

def create_resume_pdf_from_job_details(parameters: dict, llm_api_key: str, job_title: str, company_name: str, job_description: str):
    """
    Logic to create a CV tailored for a specific job without requiring a URL.
    
    Args:
        parameters: Configuration parameters dictionary
        llm_api_key: API key for language model
        job_title: Title of the job
        company_name: Name of the company
        job_description: Full job description text
    """
    try:
        logger.info(f"Generating a tailored resume for {job_title} at {company_name}")

        # Load the plain text resume
        with open(parameters["uploads"]["plainTextResume"], "r", encoding="utf-8") as file:
            plain_text_resume = file.read()

        # Initialize StyleManager
        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning("No styles available. Proceeding without style selection.")
        else:
            # Present style choices to the user
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for style_name, (file_name, author_link) in available_styles.items():
                    if selected_choice.startswith(style_name):
                        style_manager.set_selected_style(style_name)
                        logger.info(f"Selected style: {style_name}")
                        break
            else:
                logger.warning("No style selected. Proceeding with default style.")

        # Initialize the Resume Generator
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)

        # Making it headless, as it just generates the html and converts it to PDF
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        driver = init_uc_browser(options=options)

        resume_generator.set_resume_object(resume_object)

        # Create the ResumeFacade
        resume_facade = ResumeFacade(
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path("data_folder/output"),
        )
        resume_facade.set_driver(driver)
        
        # Generate tailored resume using the job details directly
        result_base64, suggested_name = resume_facade.util_create_resume_from_description(
            job_description, job_title, company_name
        )

        # Decode Base64 to binary data
        try:
            pdf_data = base64.b64decode(result_base64)
        except base64.binascii.Error as e:
            logger.error("Error decoding Base64: %s", e)
            raise

        # Create formatted company-position folder name
        company_name_safe = re.sub(r'[^\w\s-]', '', company_name).strip()
        position_name_safe = re.sub(r'[^\w\s-]', '', job_title).strip()
        safe_folder_name = f"{company_name_safe}_{position_name_safe}".replace(' ', '_')
        
        # Define the output directory
        output_dir = Path(parameters["outputFileDirectory"]) / safe_folder_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write the PDF file
        output_path = output_dir / "tailored_resume.pdf"
        try:
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            logger.info(f"Tailored resume saved at: {output_path}")
            return output_path
        except IOError as e:
            logger.error("Error writing file: %s", e)
            raise
    except Exception as e:
        logger.exception(f"An error occurred while creating the tailored resume: {e}")
        raise

def format_execution_time(seconds: float) -> str:
    """Format execution time into hours, minutes, and seconds."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining_seconds = seconds % 60

    time_parts = []
    if hours > 0:
        time_parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
    if minutes > 0:
        time_parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
    if remaining_seconds > 0 or not time_parts:  # Include seconds if no larger units or if there are remaining seconds
        time_parts.append(f"{remaining_seconds:.2f} seconds")

    return " ".join(time_parts)
        
def handle_inquiries(selected_actions: List[str], parameters: dict, llm_api_key: str):
    """
    Decide which function to call based on the selected user actions.

    :param selected_actions: List of actions selected by the user.
    :param parameters: Configuration parameters dictionary.
    :param llm_api_key: API key for the language model.
    """
    logger.info(f"Handling inquiries with selected actions: {selected_actions}")
    try:
        if selected_actions:
            start_time = time.time()
            
            if "Start job hunting" == selected_actions:
                print("Crafting a standout professional resume for each job suitable...")
                create_and_run_bot(parameters, llm_api_key)
                
            if "Generate Resume" == selected_actions:
                print("Crafting a standout professional resume...")
                # Measure time it takes to generate the resume
                create_resume_pdf(parameters, llm_api_key)
                
            if "Generate Resume Tailored for Job Description" == selected_actions:
                print("Customizing your resume to enhance your job application...")
                # Measure time it takes to generate the resume
                create_resume_pdf_tailored(parameters, llm_api_key)
                
            if "Generate Tailored Cover Letter for Job Description" == selected_actions:
                print("Designing a personalized cover letter to enhance your job application...")
                # Measure time it takes to generate the resume
                create_cover_letter(parameters, llm_api_key)

            end_time = time.time()
            execution_time = end_time - start_time
            print(f"\nTask completed in {format_execution_time(execution_time)}")
        else:
            logger.warning("No actions selected. Nothing to execute.")
    except Exception as e:
        logger.exception(f"An error occurred while handling inquiries: {e}")
        raise

def prompt_user_action() -> str:
    """
    Use inquirer to ask the user which action they want to perform.

    :return: Selected action.
    """
    try:
        questions = [
            inquirer.List(
                'action',
                message="Select the action you want to perform",
                choices=[
                    "Start job hunting",
                    "Generate Resume",
                    "Generate Resume Tailored for Job Description",
                    "Generate Tailored Cover Letter for Job Description",
                ],
            ),
        ]
        answer = inquirer.prompt(questions)
        if answer is None:
            print("No answer provided. The user may have interrupted.")
            return ""
        return answer.get('action', "")
    except Exception as e:
        print(f"An error occurred: {e}")
        return "err"


def main():
    """Main entry point for the ResumeAigent Job Application Bot."""
    try:
        # Define and validate the data folder
        data_folder = Path("data_folder")
        secrets_file, config_file, plain_text_resume_file, output_folder = FileManager.validate_data_folder(data_folder)

        # Validate configuration and secrets
        config = ConfigValidator.validate_config(config_file)
        llm_api_key = ConfigValidator.validate_secrets(secrets_file)

        # Prepare parameters
        config["uploads"] = FileManager.get_uploads(plain_text_resume_file)
        config["outputFileDirectory"] = output_folder
        logger.debug("About to handle inquiries")

        # Interactive prompt for user to select actions
        selected_actions = prompt_user_action()
        logger.info(f"Selected action: {selected_actions}")

        # Handle selected actions and execute them
        logger.debug("About to handle inquiries")
        handle_inquiries(selected_actions, config, llm_api_key)
        logger.debug("Completed handling inquiries")
        print('Completed handling inquiries')
        return 0

    except ConfigError as ce:
        logger.error(f"Configuration error: {ce}")
        logger.error(
            "Refer to the configuration guide for troubleshooting: "
            "https://github.com/StalkerSea/ResumeAigent?tab=readme-ov-file#configuration"
        )
        return 1
    except FileNotFoundError as fnf:
        logger.error(f"File not found: {fnf}")
        logger.error("Ensure all required files are present in the data folder.")
        return 1
    except RuntimeError as re:
        logger.error(f"Runtime error: {re}")
        logger.debug(traceback.format_exc())
        return 1
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
        logger.debug(traceback.format_exc())
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)