import base64
import json
import os
import random
import sys
import re
import select
import time
import traceback
from typing import List, Optional, Any, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By

from httpx import HTTPStatusError
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

from selenium.webdriver.remote.webelement import WebElement

from src.job.context import JobContext
from src.job.application import JobApplication
from src.job.application_saver import ApplicationSaver
from src.job_portals.application_form_elements import SelectQuestion, TextBoxQuestionType
from src.job_portals.base_job_portal import BaseJobPortal

from src.app_logging import logger
from src.job.job import Job
from src.job_portal_handler.llm.llm_manager import GPTAnswerer


def question_already_exists_in_data(question: str, data: List[dict]) -> bool:
    """
    Check if a question already exists in the data list.

    Args:
        question: The question text to search for
        data: List of question dictionaries to search through

    Returns:
        bool: True if question exists, False otherwise
    """
    return any(item["question"] == question for item in data)


class JobApplier:
    def __init__(
        self,
        job_portal: BaseJobPortal,
        resume_dir: Optional[str],
        set_old_answers: List[Tuple[str, str, str]],
        gpt_answerer: GPTAnswerer,
        resume_generator_manager,
    ):
        logger.debug("Initializing EasyApplier")
        if resume_dir is None or not os.path.exists(resume_dir):
            resume_dir = None
        self.job_page = job_portal.job_page
        self.job_application_page = job_portal.application_page
        self.resume_path = resume_dir
        self.set_old_answers = set_old_answers
        self.gpt_answerer = gpt_answerer
        self.resume_generator_manager = resume_generator_manager
        #self.all_data = self._load_questions_from_json()
        self.current_job : Job | None = None
        self.driver = None

        logger.debug("EasyApplier initialized successfully")

    def _detect_language(self, text: str) -> Optional[str]:
        """
        Detect if text is primarily in English or Spanish.
        Returns 'en' for English, 'es' for Spanish, or None for other languages
        """
        # Common Spanish words that rarely appear in English
        spanish_markers = ['el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 
                          'trabajo', 'años', 'experiencia', 'desarrollador', 
                          'empresa', 'requisitos', 'conocimientos']
        
        # Common English words that rarely appear in Spanish
        english_markers = ['the', 'we', 'are', 'is', 'our', 'you', 'will', 
                          'requirements', 'experience', 'skills', 'job', 
                          'responsibilities', 'must', 'have']
        
        # Convert to lowercase and split into words
        words = text.lower().split()
        
        # Count marker words
        spanish_count = sum(1 for word in words if word in spanish_markers)
        english_count = sum(1 for word in words if word in english_markers)
        
        # Determine language based on marker counts
        if spanish_count > english_count and spanish_count > 2:
            return 'es'
        elif english_count > spanish_count and english_count > 2:
            return 'en'
        return None

    def _load_questions_from_json(self) -> List[dict]:
        output_file = "answers.json"
        logger.debug(f"Loading questions from JSON file: {output_file}")
        try:
            with open(output_file, "r") as f:
                try:
                    data = json.load(f)
                    if not isinstance(data, list):
                        raise ValueError(
                            "JSON file format is incorrect. Expected a list of questions."
                        )
                except json.JSONDecodeError:
                    logger.error("JSON decoding failed")
                    data = []
            logger.debug("Questions loaded successfully from JSON")
            return data
        except FileNotFoundError:
            logger.warning("JSON file not found, returning empty list")
            return []
        except Exception:
            tb_str = traceback.format_exc()
            logger.error(f"Error loading questions data from JSON file: {tb_str}")
            raise Exception(
                f"Error loading questions data from JSON file: \nTraceback:\n{tb_str}"
            )

    def job_apply(self, job: Job, driver: webdriver.Chrome, manual_mode: bool = False) -> bool:
        """
        Apply to a job posting with option for manual or automated process.
        
        Args:
            job: Job to apply to
            driver: Selenium WebDriver instance
            manual_mode: If True, wait for manual completion. If False, auto-fill (default: False)
        
        Returns:
            bool: True if application was successful, False otherwise
        """
        logger.debug(f"Starting {'manual' if manual_mode else 'automated'} job application for job: {job}")
        self.driver = driver
        job_context = JobContext()
        job_context.job = job
        job_context.job_application = JobApplication(job)

        try:
            # More human-like navigation with variable timing
            self.job_page.goto_job_page(job)
            
            # Add reading time - varies by job description length
            time.sleep(random.uniform(3.0, 7.0))
            
            # Get job details and validate
            job_description = self.job_page.get_job_description(job)
            
            # Reading time based on content length
            description_length = len(job_description)
            reading_time = min(8.0, max(2.0, description_length / 1000 * 1.5))  # Roughly 1.5 sec per 1000 chars
            time.sleep(random.uniform(reading_time * 0.8, reading_time * 1.2))
            
            job.set_job_description(job_description)
            
            recruiter_link = self.job_page.get_recruiter_link()
            job.set_recruiter_link(recruiter_link)
            self.current_job = job
            
            # Pass job info to GPT Answerer for evaluation
            self.gpt_answerer.set_job(job)
            
            # Check job suitability
            is_suitable = self.gpt_answerer.is_job_suitable()
            
            # For manual mode, we're done after evaluation
            if manual_mode:
                # Don't click Apply button in manual mode - just evaluate and return
                return is_suitable

            # Click apply button and handle form
            self.job_page.click_apply_button(job_context)
    
            if manual_mode:
                logger.info("Waiting for manual application completion...")
                logger.info("Press 'y' + Enter at any time to confirm manual completion")
                try:
                    while True:
                        # Check for success modal
                        success_modal = self.driver.find_elements(
                            By.CSS_SELECTOR,
                            "div.artdeco-modal__content .jpac-modal-header, " +
                            "div.artdeco-modal__content h3.jpac-modal-header"
                        )
                        
                        if success_modal:
                            modal_texts = [modal.text.lower() for modal in success_modal]
                            if any("application was sent" in text for text in modal_texts):
                                logger.info("Application success modal detected!")
                                return True
                        
                        # Check for manual confirmation without blocking
                        if self._check_for_manual_input():
                            logger.info("Manual application confirmation received")
                            return True
                        
                        time.sleep(0.5)  # Small sleep to prevent CPU overuse
                
                except KeyboardInterrupt:
                    logger.info("Application process interrupted by user")
                    return False
                    
            else:
                # Automated mode - fill form automatically
                logger.debug("Filling out application form")
                self._fill_application_form(job_context)
    
            logger.debug(f"Job application process completed successfully for job: {job}")
            return True
    
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"Failed to apply to job: {job}, error: {tb_str}")
    
            logger.debug("Saving application process due to failure")
            self.job_application_page.save()
    
            raise Exception(
                f"Failed to apply to job! Original exception:\nTraceback:\n{tb_str}"
            )

    def _check_for_manual_input(self) -> bool:
        """Non-blocking input check"""
        if select.select([sys.stdin], [], [], 0)[0]:  # Check if input is available
            user_input = input().lower()
            return user_input == 'y'
        return False

    def _fill_application_form(self, job_context: JobContext) -> None:
        job = job_context.job
        job_application = job_context.job_application
        logger.debug(f"Filling out application form for job: {job}")
    
        self.fill_up(job_context)
    
        while self.job_application_page.has_next_button():
            self.fill_up(job_context)
            self.job_application_page.click_next_button()
            self.job_application_page.handle_errors()
    
        if self.job_application_page.has_submit_button():
            # Uncheck follow company before submitting
            self.job_application_page.uncheck_follow_company()
            self.job_application_page.click_submit_button()
            ApplicationSaver.save(job_application)
            logger.debug("Application form submitted")
            return
    
        logger.warning(f"submit button not found, discarding application {job}")

    def fill_up(self, job_context: JobContext) -> None:
        job = job_context.job
        logger.debug(f"Filling up form sections for job: {job}")

        input_elements = self.job_application_page.get_input_elements()

        try:
            for element in input_elements:
                self._process_form_element(element, job_context)

        except Exception as e:
            logger.error(
                f"Failed to fill up form sections: {e} {traceback.format_exc()}"
            )

    def _process_form_element(
        self, element: WebElement, job_context: JobContext
    ) -> None:
        logger.debug(f"Processing form element {element}")
        if self.job_application_page.is_upload_field(element):
            self._handle_upload_fields(element, job_context)
        else:
            self._fill_additional_questions(job_context)

    def _handle_upload_fields(self, element: WebElement, job_context: JobContext) -> None:
        logger.debug("Handling upload fields")
    
        file_upload_elements = self.job_application_page.get_file_upload_elements()
    
        for element in file_upload_elements:
            file_upload_element_heading = self.job_application_page.get_upload_element_heading(element)
            output = self.gpt_answerer.determine_resume_or_cover(file_upload_element_heading)
    
            if "resume" in output:
                logger.debug("Handling resume upload")
                
                # First check if there are already uploaded resumes
                try:
                    resume_containers = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        "div.jobs-document-upload-redesign-card__container"
                    )
                    
                    if resume_containers:
                        # Detect language
                        lang = self._detect_language(job_context.job.description)
                        if lang is None:
                            logger.error("Job description is neither in English nor Spanish")
                            raise ValueError(
                                "Application cancelled: Job description language is not supported. "
                                "Only English and Spanish are supported."
                            )
                        
                        # Look for appropriate resume based on language
                        target_filename = "cv eng.pdf" if lang == 'en' else "cv esp.pdf"
                        logger.debug(f"Looking for resume: {target_filename}")
                        
                        for container in resume_containers:
                            try:
                                filename = container.find_element(
                                    By.CSS_SELECTOR,
                                    "h3.jobs-document-upload-redesign-card__file-name"
                                ).text
                                
                                if filename == target_filename:
                                    # Click the radio button to select this resume
                                    radio_label = container.find_element(
                                        By.CSS_SELECTOR,
                                        "label.jobs-document-upload-redesign-card__toggle-label"
                                    )
                                    radio_label.click()
                                    logger.debug(f"Selected existing resume: {filename}")
                                    return
                            except Exception as e:
                                logger.warning(f"Error processing resume container: {str(e)}")
                                continue
                                
                        logger.warning(f"Could not find appropriate resume {target_filename} in uploaded files")
                except Exception as e:
                    logger.warning(f"Error checking for existing resumes: {str(e)}")
    
                # If we get here, either there were no uploaded resumes or the right one wasn't found
                # Proceed with normal upload logic
                if self.resume_path is not None and os.path.isdir(self.resume_path):
                    # Rest of your existing resume upload logic
                    lang = self._detect_language(job_context.job.description)
                    if lang is None:
                        raise ValueError(
                            "Application cancelled: Job description language is not supported. "
                            "Only English and Spanish are supported."
                        )
                    
                    resume_filename = "cv eng.pdf" if lang == 'en' else "cv esp.pdf"
                    resume_file_path = os.path.join(self.resume_path, resume_filename)
                    
                    if os.path.isfile(resume_file_path):
                        self.job_application_page.upload_file(element, resume_file_path)
                        job_context.job.resume_path = resume_file_path
                        job_context.job_application.resume_path = str(resume_file_path)
                        logger.debug(f"Resume uploaded from path: {resume_file_path}")
                    else:
                        logger.warning(f"Resume file not found: {resume_file_path}")
                        self._create_and_upload_resume(element, job_context)
                else:
                    logger.debug("Resume path not found or invalid, generating new resume")
                    self._create_and_upload_resume(element, job_context)
    
            elif "cover" in output:
                logger.debug("Uploading cover letter")
                self._create_and_upload_cover_letter(element, job_context)
    
        logger.debug("Finished handling upload fields")

    def _create_and_upload_resume(self, element, job_context: JobContext):
        job = job_context.job
        job_application = job_context.job_application
        logger.debug("Starting the process of creating and uploading resume.")
        folder_path = "generated_cv"

        try:
            if not os.path.exists(folder_path):
                logger.debug(f"Creating directory at path: {folder_path}")
            os.makedirs(folder_path, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create directory: {folder_path}. Error: {e}")
            raise

        while True:
            try:
                timestamp = int(time.time())
                file_path_pdf = os.path.join(folder_path, f"CV_{timestamp}.pdf")
                logger.debug(f"Generated file path for resume: {file_path_pdf}")

                logger.debug(f"Generating resume for job: {job.title} at {job.company}")
                resume_pdf_base64 = self.resume_generator_manager.pdf_base64(
                    job_description_text=job.description
                )
                with open(file_path_pdf, "xb") as f:
                    f.write(base64.b64decode(resume_pdf_base64))
                logger.debug(
                    f"Resume successfully generated and saved to: {file_path_pdf}"
                )

                break
            except HTTPStatusError as e:
                if e.response.status_code == 429:

                    retry_after = e.response.headers.get("retry-after")
                    retry_after_ms = e.response.headers.get("retry-after-ms")

                    if retry_after:
                        wait_time = int(retry_after)
                        logger.warning(
                            f"Rate limit exceeded, waiting {wait_time} seconds before retrying..."
                        )
                    elif retry_after_ms:
                        wait_time = int(retry_after_ms) / 1000.0
                        logger.warning(
                            f"Rate limit exceeded, waiting {wait_time} milliseconds before retrying..."
                        )
                    else:
                        wait_time = 20
                        logger.warning(
                            f"Rate limit exceeded, waiting {wait_time} seconds before retrying..."
                        )

                    time.sleep(wait_time)
                else:
                    logger.error(f"HTTP error: {e}")
                    raise

            except Exception as e:
                logger.error(f"Failed to generate resume: {e}")
                tb_str = traceback.format_exc()
                logger.error(f"Traceback: {tb_str}")
                if "RateLimitError" in str(e):
                    logger.warning("Rate limit error encountered, retrying...")
                    time.sleep(20)
                else:
                    raise

        file_size = os.path.getsize(file_path_pdf)
        max_file_size = 2 * 1024 * 1024  # 2 MB
        logger.debug(f"Resume file size: {file_size} bytes")
        if file_size > max_file_size:
            logger.error(f"Resume file size exceeds 2 MB: {file_size} bytes")
            raise ValueError("Resume file size exceeds the maximum limit of 2 MB.")

        allowed_extensions = {".pdf", ".doc", ".docx"}
        file_extension = os.path.splitext(file_path_pdf)[1].lower()
        logger.debug(f"Resume file extension: {file_extension}")
        if file_extension not in allowed_extensions:
            logger.error(f"Invalid resume file format: {file_extension}")
            raise ValueError(
                "Resume file format is not allowed. Only PDF, DOC, and DOCX formats are supported."
            )

        try:
            logger.debug(f"Uploading resume from path: {file_path_pdf}")
            element.send_keys(os.path.abspath(file_path_pdf))
            job.resume_path = os.path.abspath(file_path_pdf)
            job_application.resume_path = os.path.abspath(file_path_pdf)
            time.sleep(2)
            logger.debug(f"Resume created and uploaded successfully: {file_path_pdf}")
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"Resume upload failed: {tb_str}")
            raise Exception(f"Upload failed: \nTraceback:\n{tb_str}")

    def _create_and_upload_cover_letter(
        self, element: WebElement, job_context: JobContext
    ) -> None:
        job = job_context.job
        logger.debug("Starting the process of creating and uploading cover letter.")

        cover_letter_text = self.gpt_answerer.answer_question_textual_wide_range(
            "Write a cover letter"
        )

        folder_path = "generated_cv"

        try:

            if not os.path.exists(folder_path):
                logger.debug(f"Creating directory at path: {folder_path}")
            os.makedirs(folder_path, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create directory: {folder_path}. Error: {e}")
            raise

        while True:
            try:
                timestamp = int(time.time())
                file_path_pdf = os.path.join(
                    folder_path, f"Cover_Letter_{timestamp}.pdf"
                )
                logger.debug(f"Generated file path for cover letter: {file_path_pdf}")

                c = canvas.Canvas(file_path_pdf, pagesize=A4)
                page_width, page_height = A4
                text_object = c.beginText(50, page_height - 50)
                text_object.setFont("Helvetica", 12)

                max_width = page_width - 100
                bottom_margin = 50
                available_height = page_height - bottom_margin - 50

                def split_text_by_width(text, font, font_size, max_width):
                    wrapped_lines = []
                    for line in text.splitlines():

                        if stringWidth(line, font, font_size) > max_width:
                            words = line.split()
                            new_line = ""
                            for word in words:
                                if (
                                    stringWidth(new_line + word + " ", font, font_size)
                                    <= max_width
                                ):
                                    new_line += word + " "
                                else:
                                    wrapped_lines.append(new_line.strip())
                                    new_line = word + " "
                            wrapped_lines.append(new_line.strip())
                        else:
                            wrapped_lines.append(line)
                    return wrapped_lines

                lines = split_text_by_width(
                    cover_letter_text, "Helvetica", 12, max_width
                )

                for line in lines:
                    text_height = text_object.getY()
                    if text_height > bottom_margin:
                        text_object.textLine(line)
                    else:

                        c.drawText(text_object)
                        c.showPage()
                        text_object = c.beginText(50, page_height - 50)
                        text_object.setFont("Helvetica", 12)
                        text_object.textLine(line)

                c.drawText(text_object)
                c.save()
                logger.debug(
                    f"Cover letter successfully generated and saved to: {file_path_pdf}"
                )

                break
            except Exception as e:
                logger.error(f"Failed to generate cover letter: {e}")
                tb_str = traceback.format_exc()
                logger.error(f"Traceback: {tb_str}")
                raise

        file_size = os.path.getsize(file_path_pdf)
        max_file_size = 2 * 1024 * 1024  # 2 MB
        logger.debug(f"Cover letter file size: {file_size} bytes")
        if file_size > max_file_size:
            logger.error(f"Cover letter file size exceeds 2 MB: {file_size} bytes")
            raise ValueError(
                "Cover letter file size exceeds the maximum limit of 2 MB."
            )

        allowed_extensions = {".pdf", ".doc", ".docx"}
        file_extension = os.path.splitext(file_path_pdf)[1].lower()
        logger.debug(f"Cover letter file extension: {file_extension}")
        if file_extension not in allowed_extensions:
            logger.error(f"Invalid cover letter file format: {file_extension}")
            raise ValueError(
                "Cover letter file format is not allowed. Only PDF, DOC, and DOCX formats are supported."
            )

        try:

            logger.debug(f"Uploading cover letter from path: {file_path_pdf}")
            element.send_keys(os.path.abspath(file_path_pdf))
            job.cover_letter_path = os.path.abspath(file_path_pdf)
            job_context.job_application.cover_letter_path = os.path.abspath(
                file_path_pdf
            )
            time.sleep(2)
            logger.debug(
                f"Cover letter created and uploaded successfully: {file_path_pdf}"
            )
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"Cover letter upload failed: {tb_str}")
            raise Exception(f"Upload failed: \nTraceback:\n{tb_str}")

    def _fill_additional_questions(self, job_context: JobContext) -> None:
        logger.debug("Filling additional questions")
        form_sections = self.job_application_page.get_form_sections()
        for section in form_sections:
            self._process_form_section(job_context, section)

    def _process_form_section(
        self, job_context: JobContext, section: WebElement
    ) -> None:
        logger.debug("Processing form section")
        if self.job_application_page.is_terms_of_service(section):
            logger.debug("Handled terms of service")
            self.job_application_page.accept_terms_of_service(section)
            return

        if self.job_application_page.is_radio_question(section):
            radio_question = self.job_application_page.web_element_to_radio_question(
                section
            )
            self._handle_radio_question(job_context, radio_question, section)
            logger.debug("Handled radio button")
            return

        if self.job_application_page.is_textbox_question(section):
            self._handle_textbox_question(job_context, section)
            logger.debug("Handled textbox question")
            return

        if self.job_application_page.is_dropdown_question(section):
            self._handle_dropdown_question(job_context, section)
            logger.debug("Handled dropdown question")
            return

    def _handle_radio_question(
        self,
        job_context: JobContext,
        radio_question: SelectQuestion,
        section: WebElement,
    ) -> None:
        job_application = job_context.job_application

        question_text = radio_question.question
        options = radio_question.options

        existing_answer = None
        current_question_sanitized = self._sanitize_text(question_text)
        for item in self.all_data:
            if (
                current_question_sanitized in item["question"]
                and item["type"] == "radio"
            ):
                existing_answer = item
                break

        if existing_answer:
            self.job_application_page.select_radio_option(
                section, existing_answer["answer"]
            )
            job_application.save_application_data(existing_answer)
            logger.debug("Selected existing radio answer")
            return

        answer = self.gpt_answerer.answer_question_from_options(question_text, options)
        self._save_questions_to_json(
            {"type": "radio", "question": question_text, "answer": answer}
        )
        #self.all_data = self._load_questions_from_json()
        job_application.save_application_data(
            {"type": "radio", "question": question_text, "answer": answer}
        )
        self.job_application_page.select_radio_option(section, answer)
        logger.debug("Selected new radio answer")
        return

    def _handle_textbox_question(
        self, job_context: JobContext, section: WebElement
    ) -> None:

        textbox_question = self.job_application_page.web_element_to_textbox_question(
            section
        )

        question_text = textbox_question.question
        question_type = textbox_question.type.value
        is_cover_letter = "cover letter" in question_text.lower()
        is_numeric = textbox_question.type is TextBoxQuestionType.NUMERIC

        # Look for existing answer if it's not a cover letter field
        existing_answer = None
        if not is_cover_letter:
            current_question_sanitized = self._sanitize_text(question_text)
            for item in self.all_data:
                if (
                    item["question"] == current_question_sanitized
                    and item.get("type") == question_type
                ):
                    existing_answer = item["answer"]
                    logger.debug(f"Found existing answer: {existing_answer}")
                    break

        if existing_answer and not is_cover_letter:
            answer = existing_answer
            logger.debug(f"Using existing answer: {answer}")
        else:
            if is_numeric:
                answer = self.gpt_answerer.answer_question_numeric(question_text)
                logger.debug(f"Generated numeric answer: {answer}")
            else:
                answer = self.gpt_answerer.answer_question_textual_wide_range(
                    question_text
                )
                logger.debug(f"Generated textual answer: {answer}")

        # Save non-cover letter answers
        if not is_cover_letter and not existing_answer:
            self._save_questions_to_json(
                {"type": question_type, "question": question_text, "answer": answer}
            )
            #self.all_data = self._load_questions_from_json()
            logger.debug("Saved non-cover letter answer to JSON.")

        self.job_application_page.fill_textbox_question(section, answer)
        logger.debug("Entered answer into the textbox.")

        job_context.job_application.save_application_data(
            {"type": question_type, "question": question_text, "answer": answer}
        )

        return

    def _handle_dropdown_question(
        self, job_context: JobContext, section: WebElement
    ) -> None:
        job_application = job_context.job_application

        dropdown = self.job_application_page.web_element_to_dropdown_question(section)

        question_text = dropdown.question
        existing_answer = None
        current_question_sanitized = self._sanitize_text(question_text)
        options = dropdown.options

        for item in self.all_data:
            if (
                current_question_sanitized in item["question"]
                and item["type"] == "dropdown"
            ):
                existing_answer = item["answer"]
                break

        if existing_answer:
            logger.debug(
                f"Found existing answer for question '{question_text}': {existing_answer}"
            )
            job_application.save_application_data(
                {
                    "type": "dropdown",
                    "question": question_text,
                    "answer": existing_answer,
                }
            )

            answer = existing_answer

        else:
            logger.debug(
                f"No existing answer found, querying model for: {question_text}"
            )
            answer = self.gpt_answerer.answer_question_from_options(
                question_text, options
            )
            self._save_questions_to_json(
                {
                    "type": "dropdown",
                    "question": question_text,
                    "answer": answer,
                }
            )
            #self.all_data = self._load_questions_from_json()
            job_application.save_application_data(
                {
                    "type": "dropdown",
                    "question": question_text,
                    "answer": answer,
                }
            )

        self.job_application_page.select_dropdown_option(section, answer)
        logger.debug(f"Selected new dropdown answer: {answer}")
        return

    def _save_questions_to_json(self, question_data: dict) -> None:
        output_file = "answers.json"
        question_data["question"] = self._sanitize_text(question_data["question"])

        logger.debug(f"Checking if question data already exists: {question_data}")
        try:
            with open(output_file, "r+") as f:
                try:
                    data = json.load(f)
                    if not isinstance(data, list):
                        raise ValueError(
                            "JSON file format is incorrect. Expected a list of questions."
                        )
                except json.JSONDecodeError:
                    logger.error("JSON decoding failed")
                    data = []

                should_be_saved: bool = not question_already_exists_in_data(
                    question_data["question"], data
                ) and not self.answer_contians_company_name(question_data["answer"])

                if should_be_saved:
                    logger.debug("New question found, appending to JSON")
                    data.append(question_data)
                    f.seek(0)
                    json.dump(data, f, indent=4)
                    f.truncate()
                    logger.debug("Question data saved successfully to JSON")
                else:
                    logger.debug("Question already exists, skipping save")
        except FileNotFoundError:
            logger.warning("JSON file not found, creating new file")
            with open(output_file, "w") as f:
                json.dump([question_data], f, indent=4)
            logger.debug("Question data saved successfully to new JSON file")
        except Exception:
            tb_str = traceback.format_exc()
            logger.error(f"Error saving questions data to JSON file: {tb_str}")
            raise Exception(
                f"Error saving questions data to JSON file: \nTraceback:\n{tb_str}"
            )

    def _sanitize_text(self, text: str) -> str:
        sanitized_text = text.lower().strip().replace('"', "").replace("\\", "")
        sanitized_text = (
            re.sub(r"[\x00-\x1F\x7F]", "", sanitized_text)
            .replace("\n", " ")
            .replace("\r", "")
            .rstrip(",")
        )
        logger.debug(f"Sanitized text: {sanitized_text}")
        return sanitized_text

    def _find_existing_answer(self, question_text):
        for item in self.all_data:
            if self._sanitize_text(item["question"]) == self._sanitize_text(
                question_text
            ):
                return item
        return None

    def answer_contians_company_name(self, answer: Any) -> bool:
        return (
            isinstance(answer, str)
            and self.current_job is not None
            and self.current_job.company is not None
            and self.current_job.company in answer
        )
