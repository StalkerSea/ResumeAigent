import random
import time
import traceback
from src.job.job import Job
from src.job.context import JobContext
from src.job_portals.base_job_portal import BaseJobPage
from src.app_logging import logger
from src.utils import browser_utils
from src.utils.constants import POPULAR_BLUE_PORTAL
import src.utils.time_utils as timeUtils
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains



class PopularBluePortalApplyJobPage(BaseJobPage):

    def __init__(self, driver):
        super().__init__(driver)

    def goto_job_page(self, job: Job):
        try:
            self.driver.get(job.link)
            logger.debug(f"Navigated to job link: {job.link}")
        except Exception as e:
            logger.error(f"Failed to navigate to job link: {job.link}, error: {str(e)}")
            raise e

        timeUtils.medium_sleep()
        self.check_for_premium_redirect(job)
    
    def get_apply_button(self, job_context: JobContext) -> WebElement:
        return self.get_easy_apply_button(job_context)

    def check_for_premium_redirect(self, job: Job, max_attempts=3):

        current_url = self.driver.current_url
        attempts = 0

        while f"{POPULAR_BLUE_PORTAL}.com/premium" in current_url and attempts < max_attempts:
            logger.warning(
                f"Redirected to {POPULAR_BLUE_PORTAL} Premium page. Attempting to return to job page."
            )
            attempts += 1

            self.driver.get(job.link)
            time.sleep(2)
            current_url = self.driver.current_url

        if f"{POPULAR_BLUE_PORTAL}.com/premium" in current_url:
            logger.error(
                f"Failed to return to job page after {max_attempts} attempts. Cannot apply for the job."
            )
            raise Exception(
                f"Redirected to {POPULAR_BLUE_PORTAL} Premium page and failed to return after {max_attempts} attempts. Job application aborted."
            )
    
    def click_apply_button(self, job_context: JobContext) -> None:
        easy_apply_button = self.get_easy_apply_button(job_context)
        logger.debug("Attempting to click 'Easy Apply' button")
        actions = ActionChains(self.driver)
        actions.move_to_element(easy_apply_button).click().perform()
        logger.debug("'Easy Apply' button clicked successfully")

        

    def get_easy_apply_button(self, job_context: JobContext) -> WebElement:
        self.driver.execute_script("document.activeElement.blur();")
        logger.debug("Focus removed from the active element")

        self.check_for_premium_redirect(job_context.job)

        easy_apply_button = self._find_easy_apply_button(job_context)
        return easy_apply_button

    def _find_easy_apply_button(self, job_context: JobContext) -> WebElement:
        logger.debug("Searching for 'Easy Apply' button")
        attempt = 0

        # First check if a job is no longer accepting applications
        try:
            no_applications_element = self.driver.find_element(
                By.XPATH,
                "//span[contains(@class, 'artdeco-inline-feedback__message') and contains(text(), 'No longer accepting applications')]"
            )
            if no_applications_element:
                logger.warning("Job is no longer accepting applications")
                raise Exception("Job posting is no longer accepting applications")
        except NoSuchElementException:
            # Continue with normal flow if element not found
            pass

        search_methods = [
            {
                "description": "find all 'Easy Apply' buttons using find_elements",
                "find_elements": True,
                "xpath": '//button[contains(@class, "jobs-apply-button") and contains(., "Easy Apply")]',
            },
            {
                "description": "'aria-label' containing 'Easy Apply to'",
                "xpath": '//button[contains(@aria-label, "Easy Apply to")]',
            },
            {
                "description": "button text search",
                "xpath": '//button[contains(text(), "Easy Apply") or contains(text(), "Apply now")]',
            },
        ]

        while attempt < 2:
            self.check_for_premium_redirect(job_context.job)
            self._scroll_page()

            for method in search_methods:
                try:
                    logger.debug(f"Attempting search using {method['description']}")

                    if method.get("find_elements"):
                        buttons = self.driver.find_elements(By.XPATH, method["xpath"])
                        if buttons:
                            for index, button in enumerate(buttons):
                                try:
                                    WebDriverWait(self.driver, 10).until(
                                        EC.visibility_of(button)
                                    )
                                    WebDriverWait(self.driver, 10).until(
                                        EC.element_to_be_clickable(button)
                                    )
                                    logger.debug(
                                        f"Found 'Easy Apply' button {index + 1}, attempting to click"
                                    )
                                    return button
                                except Exception as e:
                                    logger.warning(
                                        f"Button {index + 1} found but not clickable: {e}"
                                    )
                        else:
                            raise TimeoutException("No 'Easy Apply' buttons found")
                    else:
                        button = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, method["xpath"]))
                        )
                        WebDriverWait(self.driver, 10).until(EC.visibility_of(button))
                        WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable(button)
                        )
                        logger.debug("Found 'Easy Apply' button, attempting to click")
                        return button

                except TimeoutException:
                    logger.warning(
                        f"Timeout during search using {method['description']}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to click 'Easy Apply' button using {method['description']} on attempt {attempt + 1}: {e}"
                    )

            self.check_for_premium_redirect(job_context.job)

            if attempt == 0:
                logger.debug("Refreshing page to retry finding 'Easy Apply' button")
                self.driver.refresh()
                time.sleep(random.randint(3, 5))
            attempt += 1

        page_url = self.driver.current_url
        logger.error(
            f"No clickable 'Easy Apply' button found after 2 attempts. page url: {page_url}"
        )
        raise Exception("No clickable 'Easy Apply' button found")

    def _scroll_page(self) -> None:
        logger.debug("Scrolling the page")
        scrollable_element = self.driver.find_element(By.TAG_NAME, "html")
        browser_utils.scroll_more_human_like(
            self.driver, scrollable_element, step=300, reverse=False
        )
        browser_utils.scroll_more_human_like(
            self.driver, scrollable_element, step=300, reverse=True
        )
    
    def get_job_description(self, job: Job) -> str:
        """Get job description with improved content extraction"""
        self.check_for_premium_redirect(job)
        logger.debug("Getting job description")
        
        try:
            # Try to click 'see more' if present
            try:
                see_more_button = self.driver.find_element(
                    By.XPATH, '//button[@aria-label="Click to see more description"]'
                )
                actions = ActionChains(self.driver)
                actions.move_to_element(see_more_button).click().perform()
                time.sleep(2)
            except NoSuchElementException:
                logger.debug("See more button not found, skipping")
    
            # Find description container with multiple possible selectors
            description_selectors = [
                "div.jobs-box__html-content.jobs-description-content__text--stretch",
                "div.jobs-description-content__text",
                "div.job-details-about-the-job-module__description"
            ]
    
            description_element = None
            for selector in description_selectors:
                try:
                    description_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if description_element:
                        break
                except NoSuchElementException:
                    continue
    
            if not description_element:
                raise NoSuchElementException("Could not find job description container")
    
            # Extract and clean the description text
            description = description_element.get_attribute('innerText')
            
            # Remove extra whitespace and normalize line breaks
            description = " ".join(
                line.strip() 
                for line in description.split('\n') 
                if line.strip()
            )
    
            logger.debug("Job description retrieved successfully")
            return description
    
        except NoSuchElementException as e:
            logger.error(f"Job description not found: {str(e)}")
            logger.debug(traceback.format_exc())
            raise Exception(f"Job description not found: {str(e)}")
        except Exception as e:
            logger.error(f"Error getting Job description: {str(e)}")
            logger.debug(traceback.format_exc())
            raise Exception(f"Error getting Job description: {str(e)}")
    
    def get_recruiter_link(self) -> str:
        logger.debug("Getting job recruiter information")
        try:
            hiring_team_section = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//h2[text()="Meet the hiring team"]')
                )
            )
            logger.debug("Hiring team section found")

            recruiter_elements = hiring_team_section.find_elements(
                By.XPATH, f'.//following::a[contains(@href, "{POPULAR_BLUE_PORTAL}.com/in/")]'
            )

            if recruiter_elements:
                recruiter_element = recruiter_elements[0]
                recruiter_link = recruiter_element.get_attribute("href")
                logger.debug(
                    f"Job recruiter link retrieved successfully: {recruiter_link}"
                )
                return recruiter_link
            else:
                logger.debug("No recruiter link found in the hiring team section")
                return ""
        except Exception as e:
            #logger.warning(f"Failed to retrieve recruiter information")
            return ""
