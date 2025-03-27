import base64
from datetime import datetime
import json
import os
import random
import sys
import termios
import time
from itertools import product
from pathlib import Path
from typing import Optional, Dict
from threading import Event
from enum import Enum
from inputimeout import inputimeout, TimeoutOccurred
from src.job_portal_handler.job_applier import JobApplier
from config import JOB_APPLICATIONS_DIR, JOB_MAX_APPLICATIONS, JOB_MIN_APPLICATIONS, MANUAL_MODE, MINIMUM_WAIT_TIME_IN_SECONDS
from src.job_portals.base_job_portal import BaseJobPortal
from src.libs.resume_and_cover_builder import ResumeFacade
from src.job.job import Job
from src.app_logging import logger
from src.resume_builder.resume import Resume
from src.utils.regex_utils import look_ahead_patterns
import re
import src.utils.time_utils as timeUtils
from src.utils.anti_detection import SessionManager

class ApplicationStatus(Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"

class EnvironmentKeys:
    def __init__(self):
        logger.debug("Initializing EnvironmentKeys")
        self.skip_apply = self._read_env_key_bool("SKIP_APPLY")
        self.disable_description_filter = self._read_env_key_bool("DISABLE_DESCRIPTION_FILTER")
        logger.debug(f"EnvironmentKeys initialized: skip_apply={self.skip_apply}, disable_description_filter={self.disable_description_filter}")

    @staticmethod
    def _read_env_key(key: str) -> str:
        value = os.getenv(key, "")
        logger.debug(f"Read environment key {key}: {value}")
        return value

    @staticmethod
    def _read_env_key_bool(key: str) -> bool:
        value = os.getenv(key) == "True"
        logger.debug(f"Read environment key {key} as bool: {value}")
        return value

class SafeJobStorage:
    """Safely manages job data storage with proper file locking and backup"""
    
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.lock_file = self.output_dir / ".file_lock"
        
    def _acquire_lock(self):
        """Simple file locking to prevent corruption"""
        max_attempts = 5
        attempts = 0
        while self.lock_file.exists() and attempts < max_attempts:
            time.sleep(0.5)
            attempts += 1
            
        if self.lock_file.exists():
            logger.warning("Could not acquire file lock, proceeding anyway")
        else:
            # Create lock file
            with open(self.lock_file, 'w') as f:
                f.write(str(os.getpid()))
                
    def _release_lock(self):
        """Release the lock file"""
        if self.lock_file.exists():
            try:
                self.lock_file.unlink()
            except:
                logger.warning("Could not remove lock file")
                
    def store_job(self, job, category, reason=None):
        """Safely store a job with proper locking and backup"""
        file_path = self.output_dir / f"{category}.json"
        backup_path = self.output_dir / f"{category}.json.bak"
        
        try:
            self._acquire_lock()
            
            # Create job data
            data = {
                "company": job.company,
                "job_title": job.title,
                "link": job.link,
                "job_recruiter": job.recruiter_link,
                "job_location": job.location,
                "storage_time": datetime.now().isoformat()
            }
            
            if reason:
                data["reason"] = reason
                
            if hasattr(job, "resume_path") and job.resume_path:
                data["resume_path"] = str(Path(job.resume_path).resolve().as_uri())
            
            # Read existing data with backup handling
            existing_data = []
            if file_path.exists():
                # Create backup before modifying
                import shutil
                shutil.copy(file_path, backup_path)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            existing_data = [existing_data]
                except (json.JSONDecodeError, UnicodeDecodeError):
                    logger.error(f"Error reading {file_path}, using backup")
                    try:
                        with open(backup_path, 'r', encoding='utf-8') as f:
                            existing_data = json.load(f)
                            if not isinstance(existing_data, list):
                                existing_data = [existing_data]
                    except:
                        logger.error("Backup also corrupt, starting fresh")
                        existing_data = []
            
            # Add new data and write back
            existing_data.append(data)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=4)
                
            logger.debug(f"Successfully stored job in {category}.json")
            
        finally:
            self._release_lock()

class JobManager:
    def __init__(self, job_portal : BaseJobPortal):
        logger.debug("Initializing JobManager")
        self.job_portal = job_portal
        self.set_old_answers = set()
        self.easy_applier_component = None
        self.last_application_time = None
        self.min_delay_between_apps = 45  # seconds
        self.status = ApplicationStatus.RUNNING
        self.pause_event = Event()
        self.stats: Dict[str, int] = {
            "applied": 0,
            "skipped": 0,
            "failed": 0
        }
        # Add session manager
        self.session_manager = SessionManager()

        self.job_storage = SafeJobStorage(JOB_APPLICATIONS_DIR)
        
        # More natural, varying delays
        self.min_delay_between_apps = random.uniform(45, 75)  # More variable delays
        
        logger.debug("JobManager initialized successfully")

    def handle_user_input(self) -> None:
        """Handle user input for pause/resume/stop"""
        try:
            user_input = inputimeout(
                prompt="Press 'p' to pause, 'r' to resume, 'q' to quit, or Enter to continue: ",
                timeout=5
            ).strip().lower()

            if user_input == 'p':
                self.pause_application()
            elif user_input == 'r':
                self.resume_application()
            elif user_input == 'q':
                self.stop_application()
        except TimeoutOccurred:
            pass

    def pause_application(self) -> None:
        """Pause the application process"""
        if self.status == ApplicationStatus.RUNNING:
            logger.info("Pausing application process... (Press 'r' to resume)")
            self.status = ApplicationStatus.PAUSED
            self.pause_event.clear()

    def resume_application(self) -> None:
        """Resume the application process"""
        if self.status == ApplicationStatus.PAUSED:
            logger.info("Resuming application process...")
            self.status = ApplicationStatus.RUNNING
            self.pause_event.set()

    def stop_application(self) -> None:
        """Stop the application process"""
        logger.info("Stopping application process...")
        self.status = ApplicationStatus.STOPPED
        self.show_application_stats()

    def show_application_stats(self) -> None:
        """Display application statistics"""
        logger.info("\nApplication Statistics:")
        logger.info(f"Total applications submitted: {self.stats['applied']}")
        logger.info(f"Total jobs skipped: {self.stats['skipped']}")
        logger.info(f"Total failures: {self.stats['failed']}")

    def set_parameters(self, parameters, resume_object=None):
        logger.debug("Setting parameters for JobManager")
        self.company_blacklist = parameters.get('company_blacklist', []) or []
        self.title_blacklist = parameters.get('title_blacklist', []) or []
        self.location_blacklist = parameters.get('location_blacklist', []) or []
        self.positions = parameters.get('positions', [])
        self.locations = parameters.get('locations', [])
        self.apply_once_at_company = parameters.get('apply_once_at_company', False)
        self.seen_jobs = []

        self.min_applicants = JOB_MIN_APPLICATIONS
        self.max_applicants = JOB_MAX_APPLICATIONS

        # Generate regex patterns from blacklist lists
        self.title_blacklist_patterns = look_ahead_patterns(self.title_blacklist)
        self.company_blacklist_patterns = look_ahead_patterns(self.company_blacklist)
        self.location_blacklist_patterns = look_ahead_patterns(self.location_blacklist)

        resume_path = parameters.get('uploads', {}).get('resume', None)
        self.resume_path = Path(resume_path) if resume_path and Path(resume_path).exists() else None
        self.resume_object = resume_object
        self.output_file_directory = Path(parameters['outputFileDirectory'])
        self.env_config = EnvironmentKeys()
        logger.debug("Parameters set successfully")

    def set_gpt_answerer(self, gpt_answerer):
        logger.debug("Setting GPT answerer")
        self.gpt_answerer = gpt_answerer

    def set_resume_generator_manager(self, resume_generator_manager):
        logger.debug("Setting resume generator manager")
        self.resume_generator_manager = resume_generator_manager

    def flush_input():
        """Flush the input buffer."""
        termios.tcflush(sys.stdin, termios.TCIOFLUSH)

    def apply_rate_limit(self):
        """Centralized rate limiting logic"""
        if not self.last_application_time:
            return
            
        time_since_last_app = (datetime.now() - self.last_application_time).total_seconds()
        if time_since_last_app < self.min_delay_between_apps:
            wait_time = self.min_delay_between_apps - time_since_last_app
            try:
                user_input = inputimeout(
                    prompt=f"Rate limit: Waiting {wait_time:.2f} seconds. Press 'y' to skip: ",
                    timeout=60
                ).strip().lower()
                if user_input != 'y':
                    time.sleep(wait_time)
            except TimeoutOccurred:
                time.sleep(wait_time)

    def handle_sleep_timer(self, duration: float, message: str) -> None:
        """Handle sleep timer with user interaction option"""
        try:
            user_input = inputimeout(
                prompt=f"{message} Press 'y' to skip, any other key to continue: ",
                timeout=60
            ).strip().lower()
            
            if user_input == 'y':
                logger.debug("User skipped waiting period")
                return
            
            logger.info(f"Waiting for {duration:.2f} seconds...")
            time.sleep(duration)
        except TimeoutOccurred:
            logger.debug("No user input received, continuing with sleep")
            time.sleep(duration)
    
    def start_collecting_data(self):
        """Collect job data with improved error handling and user interaction"""
        searches = list(product(self.positions, self.locations))
        random.shuffle(searches)
        page_count = 0
        minimum_time = 300  # 5 minutes in seconds
        next_page_time = time.time() + minimum_time
    
        for position, location in searches:
            location_url = "&location=" + location
            page_number = 0
            logger.info(f"Collecting data for {position} in {location}", color="yellow")
            
            try:
                # Add retry mechanism with increasing backoffs
                max_retries = 3
                retry_count = 0
                backoff_time = 60  # 1 minute initial backoff
                
                while retry_count < max_retries:
                    try:
                        # Page navigation
                        page_number += 1
                        page_count += 1
                        logger.info(f"Processing page {page_number}", color="yellow")
                        
                        self.job_portal.jobs_page.next_job_page(position, location_url, page_number)
                        timeUtils.medium_sleep()
                        
                        logger.info("Collecting jobs from current page", color="yellow")
                        self.read_jobs()
                        logger.info("Page data collection completed", color="yellow")
                        
                        # Handle minimum wait time between pages
                        time_until_next = next_page_time - time.time()
                        if time_until_next > 0:
                            self.handle_sleep_timer(
                                time_until_next,
                                f"Minimum wait time between pages: {time_until_next:.1f} seconds."
                            )
                        next_page_time = time.time() + minimum_time
                        
                        # Add random delays every 5 pages
                        if page_count % 5 == 0:
                            sleep_duration = random.randint(60, 300)  # 1-5 minutes
                            self.handle_sleep_timer(
                                sleep_duration,
                                f"Adding random delay of {sleep_duration/60:.1f} minutes."
                            )
                    
                    except Exception as e:
                        if "rate limit" in str(e).lower() or "too many requests" in str(e).lower():
                            retry_count += 1
                            logger.warning(f"Rate limit detected. Backing off for {backoff_time} seconds (retry {retry_count}/{max_retries})")
                            time.sleep(backoff_time)
                            backoff_time *= 2  # Exponential backoff
                        else:
                            # For non-rate-limit errors, just log and continue
                            logger.error(f"Error processing search: {str(e)}")
                            break
                        
            except Exception as e:
                logger.error(f"Error processing search {position} in {location}: {str(e)}")
                continue

    def start_applying(self):
        """Handle job application process with improved user control and rate limiting"""
        logger.debug("Starting job application process")

        # Start a new browsing session with natural timing
        self.session_manager.start_session()
    
        self.easy_applier_component = JobApplier(
            self.job_portal, 
            self.resume_path, 
            self.set_old_answers,
            self.gpt_answerer, 
            self.resume_generator_manager
        )
        
        searches = list(product(self.positions, self.locations))
        random.shuffle(searches)
        page_count = 0
        minimum_time = MINIMUM_WAIT_TIME_IN_SECONDS
        next_page_time = time.time() + minimum_time
    
        try:
            for position, location in searches:
                if self.status == ApplicationStatus.STOPPED:
                    logger.info("Application process stopped by user")
                    break
    
                location_url = "&location=" + location
                page_number = 0
                logger.info(f"Starting job search for {position} in {location}")
    
                try:
                    while self.status != ApplicationStatus.STOPPED:
                        # Check for pause state
                        while self.status == ApplicationStatus.PAUSED:
                            logger.info("Application process paused. Press 'r' to resume or 'q' to quit")
                            self.handle_user_input()
                            time.sleep(1)
                            continue
    
                        page_number += 1
                        page_count += 1
                        logger.info(f"Processing page {page_number}")
    
                        try:
                            # Check for user input before processing each page
                            self.handle_user_input()

                            # Before navigating to each new page:
                            self.job_portal.jobs_page.next_job_page(position, location_url, page_number)
                            
                            # Record the request and get natural delay
                            self.session_manager.record_request(self.job_portal.driver.current_url)
                            delay = self.session_manager.get_next_request_delay()
                            time.sleep(delay)
                            
                            # Check if we should end the session
                            if self.session_manager.should_end_session():
                                logger.warning("Daily request limit reached. Ending session to avoid detection.")
                                self.stop_application()
                                return
                            
                            timeUtils.medium_sleep()
    
                            # Get jobs from page
                            jobs = self.job_portal.jobs_page.get_jobs_from_page(scroll=True)
                            if not jobs:
                                logger.info("No more jobs found on this page")
                                break
    
                            # Apply to jobs with pause/stop checks
                            self.apply_jobs()
                            logger.info("Completed applications for current page")
    
                            # Handle rate limiting between pages
                            time_until_next = next_page_time - time.time()
                            if time_until_next > 0:
                                self.handle_sleep_timer(
                                    time_until_next,
                                    f"Rate limit: Waiting {time_until_next:.1f} seconds between pages."
                                )
                            next_page_time = time.time() + minimum_time
    
                        except Exception as e:
                            logger.error(f"Error processing page {page_number}: {str(e)}")
                            if "jobs" not in locals() or not jobs:
                                break
                            continue
    
                except Exception as e:
                    logger.error(f"Error in search for {position} in {location}: {str(e)}")
                    continue
    
        finally:
            # Always show stats when finishing
            self.show_application_stats()
            logger.info("Application process completed")

    def _apply_to_job(self, job: Job) -> None:
        """Apply to a job and record success"""
        start_time = time.time()
        
        # Apply to the job
        application_success = self.easy_applier_component.job_apply(job, self.job_portal.driver, manual_mode=MANUAL_MODE)
        
        if application_success:
            if MANUAL_MODE:
                # Create a tailored resume for this job
                try:
                    output_path = self._create_tailored_resume_for_job(job)
                    if output_path:
                        job.resume_path = str(output_path)
                        logger.info(f"Created tailored resume at: {output_path}")
                        self.write_to_file(job, "manual_apply")
                        logger.info(f"Stored application: {job.title} at {job.company}.")
                except Exception as e:
                    logger.error(f"Failed to create tailored resume: {e}")
            else:
                self.write_to_file(job, "success")
                logger.info(f"Successfully applied to: {job.title} at {job.company}")
        else:
            logger.error(f"Not applying for {job.title} at {job.company}, job score too low")
        
        # Calculate and log execution time
        end_time = time.time()
        execution_time = end_time - start_time
        formatted_time = self._format_execution_time(execution_time)
        logger.info(f"Job application process completed in {formatted_time}")
        
        # Apply rate limiting after successful application
        self.apply_rate_limit()
    
    def _create_tailored_resume_for_job(self, job: Job) -> Optional[Path]:
        """Create a tailored resume for this specific job"""
        try:
            logger.info(f"Generating tailored resume for {job.title} at {job.company}")
            
            # The resume_generator_manager should already have the style selected
            resume_generator = self.resume_generator_manager.resume_generator
            style_manager = self.resume_generator_manager.style_manager
            
            # Create a resume facade using the job description we already have
            resume_facade = ResumeFacade(            
                api_key=self.gpt_answerer.api_key,
                style_manager=style_manager,
                resume_generator=resume_generator,
                resume_object=self.resume_object,
                output_path=Path("data_folder/output"),
            ) 
            
            # Reuse existing job data instead of fetching it again
            # This is the key part that avoids duplicate LLM calls
            job_description = job.description if hasattr(job, 'description') and job.description else None
            
            if not job_description:
                # If we don't have the job description yet, we need to get it
                logger.info("Getting job description from job page")
                if self.job_portal.driver:
                    # Navigate to job page if not already there
                    if job.link and job.link not in self.job_portal.driver.current_url:
                        self.job_portal.driver.get(job.link)
                        time.sleep(2)  # Wait for page to load
                    
                    # Extract job description from current page
                    job_description = self.job_portal.jobs_page.get_job_description()
                    job.description = job_description  # Save for future use
            
            if not job_description:
                logger.warning("Could not get job description, using job title and company")
                job_description = f"Job Title: {job.title}\nCompany: {job.company}\nLocation: {job.location}"
            
            # Generate tailored resume
            result_base64, suggested_name = resume_facade.util_create_resume_from_description(
                job_description, job.title, job.company
            )
            
            # Create formatted company-position folder name
            company_name = re.sub(r'[^\w\s-]', '', job.company).strip()
            position_name = re.sub(r'[^\w\s-]', '', job.title).strip()
            safe_folder_name = f"{company_name}_{position_name}".replace(' ', '_')
            
            # Decode Base64 to binary data
            try:
                pdf_data = base64.b64decode(result_base64)
            except base64.binascii.Error as e:
                logger.error(f"Error decoding Base64: {e}")
                return None
            
            # Define output path
            output_dir = Path(JOB_APPLICATIONS_DIR) / "resumes" / safe_folder_name
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Save the PDF
            output_path = output_dir / "tailored_resume.pdf"
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            
            logger.info(f"Tailored resume saved to: {output_path}")
            return output_path
            
        except Exception as e:
            logger.exception(f"Error creating tailored resume for job: {e}")
            return None
    
    def _format_execution_time(self, seconds: float) -> str:
        """Format execution time into hours, minutes, and seconds."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        remaining_seconds = seconds % 60
    
        time_parts = []
        if hours > 0:
            time_parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
        if minutes > 0:
            time_parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
        if remaining_seconds > 0 or not time_parts:
            time_parts.append(f"{remaining_seconds:.2f} seconds")
    
        return " ".join(time_parts)

    def read_jobs(self):
        job_element_list = self.job_portal.jobs_page.get_jobs_from_page()
        job_list = [self.job_portal.jobs_page.job_tile_to_job(job_element) for job_element in job_element_list] 
        for job in job_list:            
            if self.is_blacklisted(job.title, job.company, job.link, job.location):
                logger.info(f"Blacklisted {job.title} at {job.company} in {job.location}, skipping...")
                self.write_to_file(job, "skipped")
                continue
            try:
                self.write_to_file(job,'data')
            except Exception as e:
                self.write_to_file(job, "failed")
                continue

    def apply_jobs(self):
        """Apply to jobs with applicant threshold checking and improved error handling"""
        try:
            job_element_list = self.job_portal.jobs_page.get_jobs_from_page()
            if not job_element_list:
                logger.info("No jobs found on current page")
                return
    
            job_list = [
                self.job_portal.jobs_page.job_tile_to_job(job_element) 
                for job_element in job_element_list
                if job_element  # Skip None elements
            ]
            
            # Filter out jobs with empty titles or companies
            job_list = [
                job for job in job_list 
                if job and job.title and job.title.strip() and job.company and job.company.strip()
            ]
    
            for job in job_list:
                # Check for pause/stop
                while self.status == ApplicationStatus.PAUSED:
                    self.handle_user_input()
                    time.sleep(1)
                
                if self.status == ApplicationStatus.STOPPED:
                    return

                self.handle_user_input()  # Check for user input
                logger.info(f"Processing job: {job.title} at {job.company}")
                
                # Check applicant count if available
                try:
                    applicant_count = self._get_applicant_count(job)
                    if applicant_count is not None:
                        if not self._is_applicant_count_in_range(applicant_count):
                            logger.debug(f"Skipping job due to applicant count ({applicant_count})")
                            self.write_to_file(job, "skipped", f"Applicant count {applicant_count} outside range")
                            continue
                except Exception as e:
                    logger.warning(f"Could not get applicant count: {str(e)}")
    
                # Skip if previously failed or blacklisted
                if self._should_skip_job(job):
                    self.stats['skipped'] += 1
                    continue
    
                # Apply to the job
                try:
                    if job.apply_method not in {"Continue", "Applied", "Apply"}:
                        self._apply_to_job(job)
                        self.stats['applied'] += 1
                except Exception as e:
                    self._handle_application_error(job, e)
                    self.stats['failed'] += 1
    
        except Exception as e:
            logger.error(f"Error in apply_jobs: {str(e)}", exc_info=True)
    
    def _get_applicant_count(self, job) -> Optional[int]:
        """Extract applicant count from job listing"""
        try:
            elements = self.job_portal.jobs_page.get_job_insight_elements(job)
            for element in elements:
                text = element.text.lower()
                if "applicant" in text:
                    count = ''.join(filter(str.isdigit, text))
                    if count:
                        return int(count) + 1 if "over" in text else int(count)
        except Exception:
            pass
        return None
    
    def _is_applicant_count_in_range(self, count: int) -> bool:
        """Check if applicant count is within acceptable range"""
        return self.min_applicants <= count <= self.max_applicants
    
    def _should_skip_job(self, job: Job) -> bool:
        """Check if job should be skipped based on various criteria"""
        if self.is_previously_failed_to_apply(job.link):
            logger.debug(f"Previously failed to apply for {job.title}")
            return True
            
        if self.is_blacklisted(job.title, job.company, job.link, job.location):
            logger.debug(f"Job blacklisted: {job.title}")
            self.write_to_file(job, "skipped", "Job blacklisted")
            return True
            
        if self.is_already_applied_to_job(job.title, job.company, job.link):
            self.write_to_file(job, "skipped", "Already applied to this job")
            return True
            
        if self.is_already_applied_to_company(job.company):
            self.write_to_file(job, "skipped", "Already applied to this company")
            return True
            
        return False
    
    def _handle_application_error(self, job: Job, error: Exception) -> None:
        """Handle and log job application errors"""
        error_msg = str(error)
        logger.error(f"Failed to apply for {job.title} at {job.company}: {error_msg}", exc_info=True)
        self.write_to_file(job, "failed", f"Application error: {error_msg}")

    def write_to_file(self, job : Job, file_name, reason=None):
        logger.debug(f"Writing job application result to file: {file_name}")
        self.job_storage.store_job(job, file_name, reason)

    def is_blacklisted(self, job_title, company, link, job_location):
        logger.debug(f"Checking if job is blacklisted: {job_title} at {company} in {job_location}")
        title_blacklisted = any(re.search(pattern, job_title, re.IGNORECASE) for pattern in self.title_blacklist_patterns)
        company_blacklisted = any(re.search(pattern, company, re.IGNORECASE) for pattern in self.company_blacklist_patterns)
        location_blacklisted = any(re.search(pattern, job_location, re.IGNORECASE) for pattern in self.location_blacklist_patterns)
        link_seen = link in self.seen_jobs
        is_blacklisted = title_blacklisted or company_blacklisted or location_blacklisted or link_seen
        logger.debug(f"Job blacklisted status: {is_blacklisted}")

        return is_blacklisted

    def is_already_applied_to_job(self, job_title, company, link):
        link_seen = link in self.seen_jobs
        if link_seen:
            logger.debug(f"Already applied to job: {job_title} at {company}, skipping...")
        return link_seen

    def is_already_applied_to_company(self, company):
        if not self.apply_once_at_company:
            return False

        output_files = ["success.json"]
        for file_name in output_files:
            file_path = self.output_file_directory / file_name
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    try:
                        existing_data = json.load(f)
                        for applied_job in existing_data:
                            if applied_job['company'].strip().lower() == company.strip().lower():
                                logger.debug(
                                    f"Already applied at {company} (once per company policy), skipping...")
                                return True
                    except json.JSONDecodeError:
                        continue
        return False

    def is_previously_failed_to_apply(self, link):
        file_name = "failed"
        file_path = self.output_file_directory / f"{file_name}.json"

        if not file_path.exists():
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump([], f)

        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                existing_data = json.load(f)
            except json.JSONDecodeError:
                logger.error(f"JSON decode error in file: {file_path}")
                return False
            
        for data in existing_data:
            data_link = data['link']
            if data_link == link:
                return True
                
        return False
