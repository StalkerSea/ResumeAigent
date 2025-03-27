
import random
import time
import numpy as np
from selenium.webdriver.common.action_chains import ActionChains
from src.app_logging import logger


def bezier_curve_points(start_x, start_y, end_x, end_y, num_points=15, control_point_factor=0.3):
    """Generate points along a quadratic Bezier curve for natural mouse movement"""
    # Create a control point to make the curve
    control_x = (start_x + end_x) / 2
    control_y = (start_y + end_y) / 2
    
    # Add some randomness to the control point
    control_x += random.uniform(-1, 1) * abs(end_x - start_x) * control_point_factor
    control_y += random.uniform(-1, 1) * abs(end_y - start_y) * control_point_factor
    
    # Generate points along the curve
    points = []
    for i in range(num_points):
        t = i / (num_points - 1)
        # Quadratic Bezier formula: B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2
        x = (1-t)**2 * start_x + 2*(1-t)*t*control_x + t**2 * end_x
        y = (1-t)**2 * start_y + 2*(1-t)*t*control_y + t**2 * end_y
        points.append((x, y))
    return points


def is_scrollable(element):
    scroll_height = element.get_attribute("scrollHeight")
    client_height = element.get_attribute("clientHeight")
    scrollable = int(scroll_height) > int(client_height)
    logger.debug(f"Element scrollable check: scrollHeight={scroll_height}, clientHeight={client_height}, scrollable={scrollable}")
    return scrollable


def scroll_more_human_like(driver, scrollable_element, start=0, end=None):
    """
    Scroll in a more human-like pattern with variable speeds, pauses, and occasional backtracking.
    """
    if not is_scrollable(scrollable_element):
        logger.warning("The element is not scrollable.")
        return
        
    # Get max scroll height if end not specified
    max_height = int(scrollable_element.get_attribute("scrollHeight"))
    if end is None or end > max_height:
        end = max_height
    
    current = start
    
    # Don't scroll perfectly linear - use a more human pattern
    while current < end:
        # Variable scroll chunk (humans don't scroll in perfect increments)
        chunk_size = random.randint(100, 450)
        
        # Sometimes scroll faster, sometimes slower
        scroll_speed = random.uniform(0.7, 2.0)
        
        # Occasionally pause as if reading content (more often on interesting content)
        if random.random() < 0.3:
            pause_time = random.uniform(1.0, 4.5)
            time.sleep(pause_time)
            
        # Occasionally scroll back up slightly (as if reconsidering something)
        if random.random() < 0.15 and current > start + 300:
            backtrack = random.randint(40, 200)
            driver.execute_script("arguments[0].scrollTop = arguments[1];", 
                                 scrollable_element, current - backtrack)
            time.sleep(random.uniform(0.7, 1.8))
            
        next_pos = min(current + chunk_size, end)
        driver.execute_script("arguments[0].scrollTop = arguments[1];", 
                             scrollable_element, next_pos)
        current = next_pos
        
        time.sleep(scroll_speed * 0.5)  # Variable sleep time

def remove_focus_active_element(driver):
    driver.execute_script("document.activeElement.blur();")
    logger.debug("Removed focus from active element.")

def wait_and_find_element(driver, by, selector, timeout=10):
    """Wait for and find an element with timeout"""
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, selector))
    )

def move_mouse_naturally(driver, target_element=None):
    """Move mouse in a natural, slightly curved path rather than straight line"""
    action = ActionChains(driver)
    
    # Get current mouse position or use a default starting point
    start_x, start_y = 100, 100  # Default position
    
    if target_element:
        # Get element location
        target_location = target_element.location
        target_size = target_element.size
        
        # Calculate destination point (slightly randomized within element)
        dest_x = target_location['x'] + target_size['width'] * random.uniform(0.3, 0.7)
        dest_y = target_location['y'] + target_size['height'] * random.uniform(0.3, 0.7)
        
        # Create curve points for natural movement
        points = bezier_curve_points(start_x, start_y, dest_x, dest_y, num_points=15)
        
        # Execute the mouse movement with natural timing
        for point in points:
            action.move_by_offset(point[0] - start_x, point[1] - start_y)
            start_x, start_y = point
            action.pause(random.uniform(0.01, 0.03))
        
        action.perform()
        
        # Add a small pause after reaching target
        time.sleep(random.uniform(0.1, 0.3))

# Create a wait_for_page_load function
def wait_for_page_load(driver, timeout=10):
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    
    old_page = driver.find_element("tag name", "html")
    yield
    WebDriverWait(driver, timeout).until(
        EC.staleness_of(old_page)
    )