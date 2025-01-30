"""
This module contains utility functions for the Resume and Cover Letter Builder service.
"""

# app/libs/resume_and_cover_builder/utils.py
import json
from bs4 import BeautifulSoup
import openai
import time
from datetime import datetime
from typing import Dict, List
from langchain_core.messages.ai import AIMessage
from langchain_core.prompt_values import StringPromptValue
from langchain_openai import ChatOpenAI
from .config import global_config
from loguru import logger
from requests.exceptions import HTTPError as HTTPStatusError

# Extra utils
from src.utils.constants import JOB_SELECTORS


class LLMLogger:

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    @staticmethod
    def log_request(prompts, parsed_reply: Dict[str, Dict]):
        calls_log = global_config.LOG_OUTPUT_FILE_PATH / "ai_calls.json"
        if isinstance(prompts, StringPromptValue):
            prompts = prompts.text
        elif isinstance(prompts, Dict):
            # Convert prompts to a dictionary if they are not in the expected format
            prompts = {
                f"prompt_{i+1}": prompt.content
                for i, prompt in enumerate(prompts.messages)
            }
        else:
            prompts = {
                f"prompt_{i+1}": prompt.content
                for i, prompt in enumerate(prompts.messages)
            }

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Extract token usage details from the response
        token_usage = parsed_reply["usage_metadata"]
        output_tokens = token_usage["output_tokens"]
        input_tokens = token_usage["input_tokens"]
        total_tokens = token_usage["total_tokens"]

        # Extract model details from the response
        model_name = parsed_reply["response_metadata"]["model_name"]
        prompt_price_per_token = 0.00000015
        completion_price_per_token = 0.0000006

        # Calculate the total cost of the API call
        total_cost = (input_tokens * prompt_price_per_token) + (
            output_tokens * completion_price_per_token
        )

        # Create a log entry with all relevant information
        log_entry = {
            "model": model_name,
            "time": current_time,
            "prompts": prompts,
            "replies": parsed_reply["content"],  # Response content
            "total_tokens": total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_cost": total_cost,
        }

        # Write the log entry to the log file in JSON format
        with open(calls_log, "a", encoding="utf-8") as f:
            json_string = json.dumps(log_entry, ensure_ascii=False, indent=4)
            f.write(json_string + "\n")

class LoggerChatModel:

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    def __call__(self, messages: List[Dict[str, str]]) -> str:
        max_retries = 15
        retry_delay = 10

        for attempt in range(max_retries):
            try:
                reply = self.llm.invoke(messages)
                parsed_reply = self.parse_llmresult(reply)
                LLMLogger.log_request(prompts=messages, parsed_reply=parsed_reply)
                return reply
            except (openai.RateLimitError, HTTPStatusError) as err:
                if isinstance(err, HTTPStatusError) and err.response.status_code == 429:
                    logger.warning(f"HTTP 429 Too Many Requests: Waiting for {retry_delay} seconds before retrying (Attempt {attempt + 1}/{max_retries})...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    wait_time = self.parse_wait_time_from_error_message(str(err))
                    logger.warning(f"Rate limit exceeded or API error. Waiting for {wait_time} seconds before retrying (Attempt {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
            except Exception as e:
                logger.error(f"Unexpected error occurred: {str(e)}, retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2

        logger.critical("Failed to get a response from the model after multiple attempts.")
        raise Exception("Failed to get a response from the model after multiple attempts.")

    def parse_llmresult(self, llmresult: AIMessage) -> Dict[str, Dict]:
        # Parse the LLM result into a structured format.
        content = llmresult.content
        response_metadata = llmresult.response_metadata
        id_ = llmresult.id
        usage_metadata = llmresult.usage_metadata

        parsed_result = {
            "content": content,
            "response_metadata": {
                "model_name": response_metadata.get("model_name", ""),
                "system_fingerprint": response_metadata.get("system_fingerprint", ""),
                "finish_reason": response_metadata.get("finish_reason", ""),
                "logprobs": response_metadata.get("logprobs", None),
            },
            "id": id_,
            "usage_metadata": {
                "input_tokens": usage_metadata.get("input_tokens", 0),
                "output_tokens": usage_metadata.get("output_tokens", 0),
                "total_tokens": usage_metadata.get("total_tokens", 0),
            },
        }
        return parsed_result

class Utils:
    """
    A utility class providing helper methods for web scraping job-related information.
    This class contains methods to handle common web scraping tasks such as:
    - Dismissing modal/overlay elements on web pages
    - Extracting job information from various job posting platforms
    - Handling platform-specific page structures (e.g., LinkedIn)
    Methods:
        click_dismiss_button(driver): 
            Removes modal/overlay elements from the webpage using JavaScript.
        get_job_info(driver): 
            Extracts and processes job description information from a webpage.
        This class expects the necessary dependencies (Selenium WebDriver, BeautifulSoup) 
        to be properly initialized and the JOB_SELECTORS global variable to be defined 
        with appropriate selector information for different job posting platforms.
    Dependencies:
        - selenium.webdriver
        - bs4.BeautifulSoup
        - logging (for logger)
    """
    @staticmethod
    def click_dismiss_button(driver):
        """
        Attempts to remove any modal or overlay elements from the webpage by hiding them via JavaScript.
        Args:
            driver: Selenium WebDriver instance used to execute JavaScript on the page
        Returns:
            bool: Always returns True since elements are hidden via JavaScript rather than clicked
        Note:
            This function uses JavaScript to directly hide elements with 'overlay' or 'modal' in their class names,
            rather than trying to click dismiss buttons. Previous implementation using click attempts is commented out.
        """
        # Maybe use these in the future? idk ¯\_ (ツ)_/¯
        # selectors = [
        #    "button[class*='modal__dismiss']",
        #    "button[aria-label*='dismiss']",
        #    "button[class*='close']"
        # ]
        
        # Remove any overlays
        driver.execute_script("""
            document.querySelectorAll('[class*="overlay"],[class*="modal"]').forEach(el => {
                el.style.display = 'none';
            });
        """)
        return True
    
    @staticmethod
    def get_job_info(driver) -> str:
        """
        Extracts job information from a web page using Selenium WebDriver.
        This method attempts to retrieve job details by trying different selectors and handling
        LinkedIn-specific page structures. It includes functionality to:
        - Click 'Show more' buttons if present
        - Handle LinkedIn's specific job detail layout
        - Clean up HTML content using BeautifulSoup
        - Remove unnecessary elements from job descriptions
        Args:
            driver (selenium.webdriver): An initialized Selenium WebDriver instance
        Returns:
            str: The extracted job description text
        Raises:
            ValueError: If the job page cannot be reached or is inaccessible
        Note:
            The method expects global JOB_SELECTORS to be defined with appropriate selector information
            for different job posting platforms.
        """
        dismiss_button_clicked = False
        for selector in JOB_SELECTORS:
            try:
                # Click the "Show more" button if it exists and not already clicked
                if not dismiss_button_clicked:
                    try:
                        dismiss_button_clicked = Utils.click_dismiss_button(driver)
                        driver.find_element("css selector", "button[class*='show-more']").click()
                    except:
                        # Button not found - likely end of content or different page structure
                        pass
                element = driver.find_element(selector["type"], selector["value"])
                
                # If this is true, then we're checking a LinkedIn job page, and we need to discard extra elements
                if selector['type'] == 'css selector' and selector["value"] == "div[class*='details']":
                    elements = driver.find_elements(selector["type"], selector["value"])
                    # Make sure that there are three elements to avoid issues
                    if len(elements) == 3:
                        # Combine text from the last two elements
                        element = elements[0]  # Keep first element
                        merged_text = elements[0].text[:100] + " " + elements[2].text # Add text from the first and last elements
                        body_element = merged_text.replace('\n', ' ').strip()
                        # Ignore the next step and break out of the loop
                        break
                else:
                    body_element = element.get_attribute(selector["attr"])
                if body_element:
                    # Parse HTML with BeautifulSoup
                    soup = BeautifulSoup(body_element, 'html.parser')
                    
                    # Find all elements with class="artdeco-card"
                    artdeco_cards = soup.find_all(class_="artdeco-card")
                    
                    # Check each artdeco-card element
                    for card in artdeco_cards:
                        # If card doesn't contain 'About the ' text and doesn't have tabindex="-1"
                        if 'About the ' not in card.text and card.get('tabindex') != '-1':
                            card.decompose()
                    
                    # Convert back to string
                    body_element = str(soup)
                    
                    # Remove the contents of all html tags, leaving only the text
                    body_element = BeautifulSoup(body_element, 'html.parser').get_text()
                    body_element.replace('\n', ' ').strip()
                    break
            except Exception as e:
                logger.debug(f"Selector {selector['value']} failed: {str(e)}")
                continue
        if body_element is None or "cannot be reached" in body_element.lower():
            logger.error("Job page cannot be reached or is inaccessible")
            driver.quit()
            raise ValueError("Failed to access job details: page cannot be reached")
        return body_element
    