from selenium.common.exceptions import NoSuchElementException, TimeoutException, NoAlertPresentException, TimeoutException, UnexpectedAlertPresentException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from src.job_portal_handler.authenticator import Authenticator
from src.app_logging import logger
import time

from src.utils.constants import POPULAR_BLUE_PORTAL

class PBPAuthenticator(Authenticator):

    def __init__(self, driver):
        self.driver = driver
        logger.debug(f"Authenticator initialized with driver: {driver}")

    @property
    def home_url(self):
        return f"https://www.{POPULAR_BLUE_PORTAL}.com"

    def handle_security_checks(self):
        # Since there are no checks needed, we can just pass
        pass

    def navigate_to_login(self):
        self.driver.get(f"https://www.{POPULAR_BLUE_PORTAL}.com/login")

    @property
    def is_logged_in(self):
        try:
            # Check for PopularBluePortal-specific element that indicates user is logged in
            # For example, the messaging button or profile icon
            #self.driver.find_element(By.CLASS_NAME, "global-nav__me-photo")
            #self.driver.find_element(By.ID, "messaging-overlay-trigger")
            self.driver.find_element(By.ID, "ember15")
            return True
        except NoSuchElementException:
            return False

    def start(self):
        logger.info("Starting Chrome browser to log in to AutoJobAigent.")
        self.driver.get(self.home_url)
        if self.is_logged_in:
            logger.info("User is already logged in. Skipping login process.")
            return
        else:
            logger.info("User is not logged in. Proceeding with login.")
            self.handle_login()

    def handle_login(self):
        try:
            logger.info("Navigating to the AutoJobAigent login page...")
            self.navigate_to_login()
            self.prompt_for_credentials()
        except NoSuchElementException as e:
            logger.error(f"Could not log in to . Element not found: {e}")
        self.handle_security_checks()


    def prompt_for_credentials(self):
        try:
            logger.debug("Enter credentials...")
            check_interval = 15  # Interval to log the current URL
            elapsed_time = 0

            while True:
                # Bring the browser window to the front
                current_window = self.driver.current_window_handle
                self.driver.switch_to.window(current_window)

                # Log current URL every 4 seconds and remind the user to log in
                current_url = self.driver.current_url
                logger.info(f"Please login on {current_url}")

                # Check if the user is already on the feed page
                if self.is_logged_in:
                    logger.debug("Login successful, redirected to feed page.")
                    break
                else:
                    # Optionally wait for the password field (or any other element you expect on the login page)
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.ID, "password"))
                    )
                    logger.debug("Password field detected, waiting for login completion.")

                time.sleep(check_interval)
                elapsed_time += check_interval

        except TimeoutException:
            logger.error("Login form not found. Aborting login.")
