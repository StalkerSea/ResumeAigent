import time
import traceback
from src.utils.constants import DATE_24_HOURS, DATE_ALL_TIME, DATE_MONTH, DATE_WEEK, POPULAR_BLUE_PORTAL
from src.job.job import Job
from src.app_logging import logger
from src.job_portals.base_job_portal import BaseJobsPage
import urllib.parse
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from src.utils import browser_utils


class PopularBluePortalJobsPage(BaseJobsPage):

    def __init__(self, driver, parameters):
        super().__init__(driver, parameters)
        self.base_search_url = self.get_base_search_url()

    def next_job_page(self, position, location, page_number):
        logger.debug(
            f"Navigating to next job page: {position} in {location}, page {page_number}"
        )
        encoded_position = urllib.parse.quote(position)
        self.driver.get(
            f"https://www.{POPULAR_BLUE_PORTAL}.com/jobs/search/{self.base_search_url}&keywords={encoded_position}{location}&start={page_number * 25}"
        )

    def job_tile_to_job(self, job_tile) -> Job:
        """Extract job information from tile based on the current LinkedIn job card structure"""
        logger.debug("Extracting job information from tile")
        job = Job()
    
        try:
            # Extract job ID from the link tracking ID
            links = job_tile.find_elements(By.CSS_SELECTOR, "a[data-control-id]")
            if links:
                job.id = links[0].get_attribute("data-control-id")
                logger.debug(f"Job ID extracted from tracking ID: {job.id}")
            else:
                # Alternative method to try to get job ID
                try:
                    job_id_match = job_tile.find_element(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
                    href = job_id_match.get_attribute("href")
                    if href and "/jobs/view/" in href:
                        job_id = href.split("/jobs/view/")[1].split("/")[0].split("?")[0]
                        job.id = job_id
                        logger.debug(f"Job ID extracted from URL: {job.id}")
                except NoSuchElementException:
                    return job
        except Exception as e:
            logger.warning(f"Error extracting job ID: {e}")
            return job
    
        try:
            # Extract job title using the exact structure from the HTML
            title_element = job_tile.find_element(
                By.CSS_SELECTOR,
                "a.job-card-list__title--link strong"
            )
            job.title = title_element.text.strip()
            logger.debug(f"Job title extracted: {job.title}")
        except NoSuchElementException:
            try:
                # Alternative selector for job title
                title_element = job_tile.find_element(
                    By.CSS_SELECTOR,
                    "a[aria-label] strong, a.disabled strong"
                )
                job.title = title_element.text.strip()
                logger.debug(f"Job title extracted (alternative): {job.title}")
            except NoSuchElementException:
                return job
    
        try:
            # Extract job link (removing tracking parameters)
            link_element = job_tile.find_element(
                By.CSS_SELECTOR,
                "a[href*='/jobs/view/']"
            )
            full_link = link_element.get_attribute("href")
            # Clean the URL by removing tracking parameters
            if "?" in full_link:
                job.link = full_link.split("?")[0]
            else:
                job.link = full_link
            logger.debug(f"Job link extracted: {job.link}")
        except NoSuchElementException:
            logger.warning("Job link is missing")
            return job
    
        try:
            # Extract company name using the exact structure from HTML
            company_element = job_tile.find_element(
                By.CSS_SELECTOR,
                "div.artdeco-entity-lockup__subtitle span"
            )
            job.company = company_element.text.strip()
            logger.debug(f"Company extracted: {job.company}")
        except NoSuchElementException:
            try:
                # Alternative selector for company name
                company_element = job_tile.find_element(
                    By.CSS_SELECTOR,
                    ".artdeco-entity-lockup__subtitle span"
                )
                job.company = company_element.text.strip()
                logger.debug(f"Company extracted (alternative): {job.company}")
            except NoSuchElementException:
                logger.warning("Company name is missing")
                return job
    
        try:
            # Extract location and work type (Hybrid/Remote/On-site)
            location_element = job_tile.find_element(
                By.CSS_SELECTOR,
                "ul.job-card-container__metadata-wrapper li span, .job-card-container__metadata-item li span"
            )
            location_text = location_element.text.strip()
            job.location = location_text
            
            # Extract work type if present
            work_types = ["Hybrid", "Remote", "On-site"]
            for work_type in work_types:
                if f"({work_type})" in location_text:
                    job.work_type = work_type
                    break
            
            logger.debug(f"Location extracted: {job.location}")
            if hasattr(job, 'work_type'):
                logger.debug(f"Work type extracted: {job.work_type}")
        except NoSuchElementException:
            logger.warning("Location information is missing")
    
        try:
            # Check for Easy Apply in the footer area
            footer_wrapper = job_tile.find_element(
                By.CSS_SELECTOR,
                "ul.job-card-list__footer-wrapper"
            )
            
            # Extract the text and check if it contains "Easy Apply"
            footer_text = footer_wrapper.text
            job.easy_apply = "Easy Apply" in footer_text
            logger.debug(f"Easy Apply: {job.easy_apply}")

            # Handle application status (Viewed/Posted time)
            if "Viewed" in footer_text:
                    job.viewed = True
                    logger.debug("Job has been viewed")
            elif "ago" in footer_text or "hour" in footer_text or "day" in footer_text:
                job.posted_time = footer_text
                logger.debug(f"Posted time: {job.posted_time}")
        except NoSuchElementException as e:
            # Try to find it anywhere in the job tile
            logger.warning(f"Error checking for Easy Apply: {str(e)}")
            job.easy_apply = False

        try:
            # Extract additional job insights if available
            insight_elements = job_tile.find_elements(
                By.CSS_SELECTOR,
                "div.job-card-container__job-insight-text, div.job-card-container__applicant-count"
            )
            
            if insight_elements:
                job.insights = "; ".join([elem.text.strip() for elem in insight_elements if elem.text.strip()])
                logger.debug(f"Job insights: {job.insights}")
        except Exception:
            logger.debug("No additional insights available")
    
        # Set defaults for missing attributes
        if not hasattr(job, 'viewed'):
            job.viewed = False
        
        if not hasattr(job, 'easy_apply'):
            job.easy_apply = False
        
        return job

    def get_jobs_from_page(self, scroll=False):
        """Get all jobs from the current page with improved duplicate detection"""
        try:
            # First check for no results
            try:
                no_jobs_element = self.driver.find_element(
                    By.CLASS_NAME, "jobs-search-no-results-banner"
                )
                if "No matching jobs found" in no_jobs_element.text or "unfortunately, things aren" in self.driver.page_source.lower():
                    logger.debug("No matching jobs found on this page, skipping.")
                    return []
            except NoSuchElementException:
                pass

            # Wait for the page to fully load
            browser_utils.wait_for_page_load(self.driver, timeout=5)
            
            # Use a more precise selector strategy matching browser console
            try:
                # First, wait for the main container to load
                browser_utils.wait_and_find_element(
                    self.driver,
                    By.CSS_SELECTOR,
                    "div.scaffold-layout__list-detail-inner.scaffold-layout__list-detail-inner--grow",
                    timeout=5
                )
                
                # Try the precise CSS selector matching browser console
                job_containers = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "div.scaffold-layout__list-detail-inner.scaffold-layout__list-detail-inner--grow div.scaffold-layout__list ul li.occludable-update div div"
                )
                
                # If we find elements with the precise selector, use those
                if job_containers:
                    logger.debug(f"Found {len(job_containers)} job elements using precise selector")
                    
                    # Remove duplicate job elements by checking their position and content
                    unique_jobs = self._filter_duplicate_jobs(job_containers)
                    logger.debug(f"After filtering duplicates: {len(unique_jobs)} unique job elements")
                    return unique_jobs
                
                # If precise selector doesn't work, try the parent elements
                logger.debug("Precise selector didn't find elements, trying parent selector")
                job_elements = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "div.scaffold-layout__list-detail-inner.scaffold-layout__list-detail-inner--grow div.scaffold-layout__list ul li.occludable-update"
                )
                
                # If no elements found, try to scroll to load more
                if not job_elements and scroll:
                    logger.debug("No job elements found initially, attempting to scroll")
                    try:
                        # Find the scrollable container
                        list_container = self.driver.find_element(
                            By.CSS_SELECTOR,
                            "div.scaffold-layout__list"
                        )
                        
                        if browser_utils.is_scrollable(list_container):
                            # Perform human-like scrolling to load content
                            browser_utils.scroll_more_human_like(self.driver, list_container, step=250, pause_time=0.5)
                            time.sleep(1.5)  # Wait for content to load
                            
                            # Try both selectors again after scrolling
                            job_containers = self.driver.find_elements(
                                By.CSS_SELECTOR,
                                "div.scaffold-layout__list-detail-inner.scaffold-layout__list-detail-inner--grow div.scaffold-layout__list ul li.occludable-update div div div"
                            )
                            
                            if job_containers:
                                logger.debug(f"Found {len(job_containers)} job elements after scrolling")
                                return job_containers
                            
                            job_elements = self.driver.find_elements(
                                By.CSS_SELECTOR,
                                "div.scaffold-layout__list-detail-inner.scaffold-layout__list-detail-inner--grow div.scaffold-layout__list ul li.occludable-update"
                            )
                    except Exception as scroll_error:
                        logger.warning(f"Error during scrolling: {str(scroll_error)}")
                    
                    if job_elements:
                        logger.debug(f"Found {len(job_elements)} job elements using parent selector")
                        unique_jobs = self._filter_duplicate_jobs(job_elements)
                        logger.debug(f"After filtering duplicates: {len(unique_jobs)} unique job elements")
                        return unique_jobs
                    
                    logger.debug("No job elements found with primary selectors, trying fallbacks")
                    
                    # Try alternative selectors in case of UI changes
                    fallback_selectors = [
                        "li.jobs-search-results__list-item",
                        "div.job-card-container",
                        "ul.jobs-search-results__list li",
                        "div.jobs-search-results-list div.job-card-list__entity-lockup"
                    ]
                    
                    for selector in fallback_selectors:
                        try:
                            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            if elements:
                                logger.debug(f"Found {len(elements)} job elements using fallback selector: {selector}")
                                return elements
                        except Exception:
                            continue
                    
                    logger.warning("No job elements found with any selector")
                    return []
                
            except NoSuchElementException as e:
                logger.warning(f"Could not find job container structure: {str(e)}")
                logger.debug(traceback.format_exc())
                return []

        except Exception as e:
            logger.error(f"Error while fetching job elements: {str(e)}")
            logger.debug(traceback.format_exc())
            return []

    def _filter_duplicate_jobs(self, job_elements):
        """Filter out duplicate job elements based on position and content"""
        unique_jobs = []
        seen_positions = set()
        seen_ids = set()
        seen_titles = {}
        
        for job_element in job_elements:
            try:
                # Try to get position
                location = job_element.location
                position_key = f"{location['x']},{location['y']}"
                
                # Try to get job ID if available
                job_id = None
                title_text = None
                
                try:
                    # Extract job ID from the link tracking ID or href
                    links = job_element.find_elements(By.CSS_SELECTOR, "a[data-control-id], a[href*='/jobs/view/']")
                    if links:
                        for link in links:
                            # Try data-control-id first
                            job_id = link.get_attribute("data-control-id")
                            if job_id:
                                break
                            
                            # If no data-control-id, try extracting from href
                            href = link.get_attribute("href")
                            if href and "/jobs/view/" in href:
                                job_id = href.split("/jobs/view/")[1].split("/")[0].split("?")[0]
                                break
                except Exception:
                    pass
                
                # If we couldn't get a job ID, try to get title text
                if not job_id:
                    try:
                        title_elements = job_element.find_elements(By.CSS_SELECTOR, "a strong, h3")
                        if title_elements:
                            title_text = title_elements[0].text.strip()
                    except Exception:
                        pass
                
                # Skip if we've seen this position, job ID, or title before
                if position_key in seen_positions:
                    continue
                    
                if job_id and job_id in seen_ids:
                    continue
                    
                if title_text:
                    # For titles, we'll also check if a similar job from the same company exists
                    company_text = None
                    try:
                        company_elements = job_element.find_elements(By.CSS_SELECTOR, ".artdeco-entity-lockup__subtitle span")
                        if company_elements:
                            company_text = company_elements[0].text.strip()
                    except Exception:
                        pass
                    
                    if company_text and title_text in seen_titles:
                        # If we've seen this title before, check if the company is also the same
                        if company_text in seen_titles[title_text]:
                            continue
                        else:
                            seen_titles[title_text].add(company_text)
                    else:
                        seen_titles[title_text] = {company_text} if company_text else set()
                
                # If we reach here, this is a unique job
                seen_positions.add(position_key)
                if job_id:
                    seen_ids.add(job_id)
                    
                unique_jobs.append(job_element)
                
            except Exception as e:
                logger.debug(f"Error while filtering job element: {e}")
                # Include the element in case of error to avoid losing legitimate jobs
                unique_jobs.append(job_element)
        
        return unique_jobs

    def get_base_search_url(self):
        parameters = self.parameters
        logger.debug("Constructing PopularBluePortal base search URL")
        url_parts = []
        working_type_filter = []
        if parameters.get("onsite") == True:
            working_type_filter.append("1")
        if parameters.get("remote") == True:
            working_type_filter.append("2")
        if parameters.get("hybrid") == True:
            working_type_filter.append("3")

        if working_type_filter:
            url_parts.append(f"f_WT={'%2C'.join(working_type_filter)}")

        experience_levels = [
            str(i + 1)
            for i, (level, v) in enumerate(
                parameters.get("experience_level", {}).items()
            )
            if v
        ]
        if experience_levels:
            url_parts.append(f"f_E={','.join(experience_levels)}")
        url_parts.append(f"distance={parameters['distance']}")
        job_types = [
            key[0].upper()
            for key, value in parameters.get("jobTypes", {}).items()
            if value
        ]
        if job_types:
            url_parts.append(f"f_JT={','.join(job_types)}")

        date_param = next(
            (
                v
                for k, v in self.DATE_MAPPING.items()
                if parameters.get("date", {}).get(k)
            ),
            "",
        )
        url_parts.append("f_LF=f_AL")  # Easy Apply
        base_url = "&".join(url_parts)
        full_url = f"?{base_url}{date_param}"
        logger.debug(f"Base search URL constructed: {full_url}")
        return full_url

    DATE_MAPPING = {
        DATE_ALL_TIME: "",
        DATE_MONTH: "&f_TPR=r2592000",
        DATE_WEEK: "&f_TPR=r604800",
        DATE_24_HOURS: "&f_TPR=r86400",
    }
