from src.job_portals.popular_blue_portal.application_page import PopularBluePortalApplicationPage
from src.job_portals.popular_blue_portal.apply_job_page import PopularBluePortalApplyJobPage
from src.job_portals.base_job_portal import BaseJobPortal
from src.job_portals.popular_blue_portal.authenticator import PBPAuthenticator
from src.job_portals.popular_blue_portal.jobs_page import PopularBluePortalJobsPage

class PopularBluePortal(BaseJobPortal):

    def __init__(self, driver, parameters):
        self.driver = driver
        self._PBPAuthenticator = PBPAuthenticator(driver)
        self._jobs_page = PopularBluePortalJobsPage(driver, parameters)
        self._application_page = PopularBluePortalApplicationPage(driver)
        self._job_page = PopularBluePortalApplyJobPage(driver)
    
    @property
    def jobs_page(self):
        return self._jobs_page

    @property
    def job_page(self):
        return self._job_page

    @property
    def authenticator(self):
        return self._PBPAuthenticator

    @property
    def application_page(self):
        return self._application_page