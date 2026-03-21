"""
Smoke test: verify Groq vision works end-to-end for UI Analyzer.
Run: python scripts/test_vision_switch.py
"""
import os
os.environ["MOCK_MODE"] = "false"

from agents import input_processor, ui_analyzer

pkg = input_processor.run("https://linear.app")
print(f"Input package ready: {len(pkg.css_tokens)} tokens, text={len(pkg.scraped_text)} chars")

profile = ui_analyzer.run(pkg)
print(f"Design category:     {profile.design_category}")
print(f"Primary color:       {profile.primary_color}")
print(f"Confidence:          {profile.confidence:.2f}")
print(f"Writing instruction: {profile.writing_instruction}")
print("Vision switch: OK")
