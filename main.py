import sys
import time
import inquirer
import traceback
from typing import List
from pathlib import Path
from src.logging import logger
from src.utils.resume import ResumeMaker
from src.utils import gen_utils as functions
from src.utils.file_manager import FileManager
from settings.localizations.manager import LocalizationManager
from src.utils.config_validator import ConfigError, ConfigValidator

class main():
    def __init__(self):
        settings = ConfigValidator.validate_app_settings("settings/settings.json")
        # Load localization settings
        self.localization_manager = LocalizationManager()
        logger.info(self.localization_manager.change_language(settings["language"]))
    
    def handle_inquiries(self, selected_actions: List[str], parameters: dict, llm_api_key: str):
        """
        Decide which function to call based on the selected user actions.

        :param selected_actions: List of actions selected by the user.
        :param parameters: Configuration parameters dictionary.
        :param llm_api_key: API key for the language model.
        """
        logger.info(f"Handling inquiries with selected actions: {selected_actions}")
        try:
            while selected_actions:  # Changed to while loop to handle menu navigation
                
                if self.localization_manager.get_string("menu/generate/resume") == selected_actions:
                    ResumeMaker.create_resume_pdf(parameters, llm_api_key)
                    break  # Exit after action is complete
                    
                elif self.localization_manager.get_string("menu/generate/resume_tailored") == selected_actions:
                    ResumeMaker.create_resume_pdf_tailored(parameters, llm_api_key)
                    break  # Exit after action is complete
                    
                elif self.localization_manager.get_string("menu/generate/cover_letter") == selected_actions:
                    ResumeMaker.create_cover_letter(parameters, llm_api_key)
                    break  # Exit after action is complete

                elif self.localization_manager.get_string("settings/prompt") == selected_actions:
                    next_action = self.open_settings_menu(parameters, llm_api_key)
                    if next_action and next_action != "err":
                        selected_actions = next_action  # Update selected_actions for next loop iteration
                        continue  # Continue to handle the new action
                    break  # Exit if no valid action returned

                break  # Exit after handling the action
        except Exception as e:
            logger.exception(f"An error occurred while handling inquiries: {e}")
            raise

    def prompt_user_action(self) -> str:
        """
        Use inquirer to ask the user which action they want to perform.

        :return: Selected action.
        """
        try:
            questions = [
                inquirer.List(
                    'action',
                    message=self.localization_manager.get_string("menu/select_action"),
                    choices=[
                        self.localization_manager.get_string("menu/generate/resume"),
                        self.localization_manager.get_string("menu/generate/resume_tailored"),
                        self.localization_manager.get_string("menu/generate/cover_letter"),
                        self.localization_manager.get_string("settings/prompt"),
                    ],
                ),
            ]
            answer = inquirer.prompt(questions)
            if answer is None:
                print(self.localization_manager.get_string("no_selection"))
                return ""
            return answer.get('action', "")
        except Exception as e:
            print(f"An error occurred: {e}")
            return "err"

    def open_settings_menu(self, parameters: dict, llm_api_key: str):
        """
        Open the settings menu for the user to modify their preferences.

        :param parameters: Configuration parameters dictionary.
        :param llm_api_key: API key for the language model.
        """
        try:
            questions = [
                inquirer.List(
                    'action',
                    message=self.localization_manager.get_string("settings/title"),
                    choices=[
                        self.localization_manager.get_string("settings/language/title"),
                        self.localization_manager.get_string("settings/return"),
                    ],
                ),
            ]
            answer = inquirer.prompt(questions)
            if answer is None:
                print(self.localization_manager.get_string("no_selection"))
                return ""
            msg = answer.get('action', "")
            if msg == self.localization_manager.get_string("settings/language/title"):
                # Prompt for new language
                languages = ["English", "Español", "Français", "Deutsch", "Italiano"]
                questions = [
                    inquirer.List(
                        'language',
                        message=self.localization_manager.get_string("settings/language/select"),
                        choices=languages,
                    ),
                ]
                answer = inquirer.prompt(questions)
                if answer is None:
                    print(self.localization_manager.get_string("no_selection"))
                    return ""
                new_language = answer.get('language', "")
                if new_language:
                    print(self.localization_manager.change_language(new_language))
                    # Go back to the previous menu after a timeout
                    time.sleep(1)
                    logger.debug(self.localization_manager.get_string("returning_to_main_menu"))
                    return self.prompt_user_action()
            elif msg == self.localization_manager.get_string("settings/return"):
                print(self.localization_manager.get_string("returning_to_main_menu"))
                # Go back to the previous menu after a timeout
                logger.debug(self.localization_manager.get_string("returning_to_main_menu"))
                return self.prompt_user_action()
                    
        except Exception as e:
            print(f"An error occurred: {e}")
            return "err"


    def main(self):
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
            selected_actions = self.prompt_user_action()
            logger.info(f"Selected action: {selected_actions}")

            # Handle selected actions and execute them
            logger.debug("About to handle inquiries")
            start_time = time.time()
            self.handle_inquiries(selected_actions, config, llm_api_key)
            end_time = time.time()
            execution_time = end_time - start_time
            formatted_time = functions.format_execution_time(execution_time)
            print(self.localization_manager.get_string("menu/thank_you").format(time=formatted_time))
            logger.debug("Task completed in %s", formatted_time)
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
    mainProgram = main()
    exit_code = mainProgram.main()
    sys.exit(exit_code)