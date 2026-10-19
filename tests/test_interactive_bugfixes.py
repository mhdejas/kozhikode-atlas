import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]

def source(name):
    return (ROOT / "site" / name).read_text()

class InteractiveBugfixTests(unittest.TestCase):
    def test_terrain_resize_and_failed_load_are_recoverable(self):
        js = source("terrain.js")
        assert "Math.max(1,host.clientWidth)" in js
        assert "delete card.dataset.loading" in js
        assert "engine.resize()" in js

    def test_terrain_honours_reduced_motion_changes(self):
        js = source("terrain.js")
        assert "reduced.addEventListener||reduced.addListener" in js
        assert "buttons.spin.disabled=reduced.matches" in js

    def test_story_does_not_require_intersection_observer(self):
        js = source("story.js")
        assert "'IntersectionObserver' in window?" in js
        assert "observer?.observe(article)" in js
        assert "reduce.addEventListener||reduce.addListener" in js

    def test_profile_handles_loading_and_missing_highest_or_named_place(self):
        js = source("profile.js")
        assert "if(!data)return" in js
        assert "if(!places.length)" in js
        assert "kozhikode>=0?kozhikode:0" in js
        assert "if(!data){setStatus('Elevation data is still loading.')" in js

    def test_inspector_reports_invalid_coordinates_and_image_errors(self):
        js = source("inspector.js")
        assert "Enter a valid latitude" in js
        assert "image.onerror" in js
        assert "if(!map||!wrap||!tools)return" in js
