"""
This module contains the FacadeManager class, which is responsible for managing the interaction between the user and other components of the application.
"""
# app/libs/resume_and_cover_builder/manager_facade.py
from datetime import datetime
import inquirer
from pathlib import Path

from loguru import logger

from src.libs.resume_and_cover_builder.llm.llm_job_parser import LLMParser
from src.job import Job
from src.libs.resume_and_cover_builder.utils import Utils
from src.utils.chrome_utils import HTML_to_PDF
from .config import global_config
from config import LLM_MODEL_TYPE, LLM_MODEL

class ResumeFacade:
    def __init__(self, api_key, style_manager, resume_generator, resume_object, output_path):
        """
        Initialize the FacadeManager with the given API key, style manager, resume generator, resume object, and log path.
        Args:
            api_key (str): The OpenAI API key to be used for generating text.
            style_manager (StyleManager): The StyleManager instance to manage the styles.
            resume_generator (ResumeGenerator): The ResumeGenerator instance to generate resumes and cover letters.
            resume_object (str): The resume object to be used for generating resumes and cover letters.
            output_path (str): The path to the log file.
        """
        lib_directory = Path(__file__).resolve().parent
        global_config.STRINGS_MODULE_RESUME_PATH = lib_directory / "resume_prompt/strings.py"
        global_config.STRINGS_MODULE_RESUME_JOB_DESCRIPTION_PATH = lib_directory / "resume_job_description_prompt/strings.py"
        global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH = lib_directory / "cover_letter_prompt/strings.py"
        global_config.STRINGS_MODULE_NAME = "strings"
        global_config.STYLES_DIRECTORY = lib_directory / "resume_style"
        global_config.LOG_OUTPUT_FILE_PATH = output_path
        global_config.API_KEY = api_key
        global_config.LLM_MODEL_TYPE = LLM_MODEL_TYPE
        global_config.LLM_MODEL = LLM_MODEL
        self.style_manager = style_manager
        self.resume_generator = resume_generator
        self.resume_generator.set_resume_object(resume_object)
        self.selected_style = None  # Property to store the selected style
        self.skills = set() # Property to store the user's skills
    
    def set_driver(self, driver):
         self.driver = driver

    def prompt_user(self, choices: list[str], message: str) -> str:
        """
        Prompt the user with the given message and choices.
        Args:
            choices (list[str]): The list of choices to present to the user.
            message (str): The message to display to the user.
        Returns:
            str: The choice selected by the user.
        """
        questions = [
            inquirer.List('selection', message=message, choices=choices),
        ]
        return inquirer.prompt(questions)['selection']

    def prompt_for_text(self, message: str) -> str:
        """
        Prompt the user to enter text with the given message.
        Args:
            message (str): The message to display to the user.
        Returns:
            str: The text entered by the user.
        """
        questions = [
            inquirer.Text('text', message=message),
        ]
        return inquirer.prompt(questions)['text']

    def link_to_job(self, job_url):
        self.driver.get(job_url)
        self.driver.implicitly_wait(3)
        
        body_element = Utils.get_job_info(self.driver)
        
        self.llm_job_parser = LLMParser(global_config)
        self.llm_job_parser.set_body_html(body_element)

        self.job = Job()
        job_details = self.llm_job_parser.extract_job_details()
        self.job.role = job_details["role"]
        self.job.company = job_details["company"]
        self.job.description = job_details["description"]
        self.job.requirements = job_details["requirements"]
        self.job.location = job_details["location"]
        logger.info(f"Extracting job details from URL: {job_url}")

    def util_create_resume_pdf_job_tailored(self) -> tuple[bytes, str]:
        """
        Create a resume PDF using the selected style and the given job description text.
        Args:
            job_url (str): The job URL to generate the hash for.
            job_description_text (str): The job description text to include in the resume.
        Returns:
            tuple: A tuple containing the PDF content as bytes and the unique filename.
        """
        style_path = self.style_manager.get_style_path()
        if style_path is None:
            raise ValueError("You must choose a style before generating the PDF.")

        html_resume = self.resume_generator.create_resume_tailored(style_path, self.job)

        # Generate a unique name using the job URL hash
        suggested_name = datetime.now().strftime('%Y-%m-%d')
        # suggested_name += hashlib.md5(self.job.link.encode()).hexdigest()[:10]
        suggested_name += "/" + self.job.company + "/" + self.job.role
        
        result = HTML_to_PDF(html_resume, self.driver)
        self.driver.quit()
        return result, suggested_name
        
    def create_resume_pdf(self) -> tuple[bytes, str]:
        """
        Create a resume PDF using the selected style and the given job description text.
        Args:
            job_url (str): The job URL to generate the hash for.
            job_description_text (str): The job description text to include in the resume.
        Returns:
            tuple: A tuple containing the PDF content as bytes and the unique filename.
        """
        style_path = self.style_manager.get_style_path()
        if style_path is None:
            raise ValueError("You must choose a style before generating the PDF.")
        
        html_resume = self.resume_generator.create_resume(style_path)
        result = HTML_to_PDF(html_resume, self.driver)
        self.driver.quit()
        return result

    def util_create_cover_letter(self) -> tuple[bytes, str]:
        """
        Create a cover letter based on the given job description text and job URL.
        Args:
            job_url (str): The job URL to generate the hash for.
            job_description_text (str): The job description text to include in the cover letter.
        Returns:
            tuple: A tuple containing the PDF content as bytes and the unique filename.
        """
        style_path = self.style_manager.get_style_path()
        if style_path is None:
            raise ValueError("You must choose a style before generating the PDF.")
        
        
        cover_letter_html = self.resume_generator.create_cover_letter_job_description(style_path, self.job.description)

        # Generate a unique name using the job URL hash
        suggested_name = self.job.role + "/" + self.job.company
        # suggested_name += hashlib.md5(self.job.link.encode()).hexdigest()[:10]
        suggested_name += "/" + datetime.now().strftime('%Y-%m-%d')

        result = HTML_to_PDF(cover_letter_html, self.driver)
        self.driver.quit()
        return result, suggested_name