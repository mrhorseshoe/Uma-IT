"""Defaults that are data rather than settings.

The skill priority list is what gets bought when a task enables skill buying
without naming any skills of its own. Tiers are the community consensus at the
time it was written; a task's own list replaces it entirely.
"""
SKILL_LEARN_PRIORITY_LIST = [
    [
        # Priority 0 - SS Tier skills (Game8 highest impact, most versatile)
        'Corner Acceleration ◯', 'Corner Adept ◯', 'Slipstream', 'Tail Held High', 
        'Straightaway Spurt', 'Ramp Up', 'Inside Scoop', 'Passing Pro', 'Homestretch Haste',
        'Fast-Paced', 'Outer Swell', 'Sprinting Gear', 'Slick Surge', 'Corner Recovery ◯',
        'Hydrate', 'After-School Stroll', 'Clean Heart', 'Dominator', 'All-Seeing Eyes', 'Mystifying Murmur'
    ],
    [
        # Priority 1 - S/A Tier skills (Game8 reliable, commonly useful)
        'Acceleration', 'Focus', 'Go with the Flow', 'I Can See Right Through You', 
        'Nimble Navigator', 'Straightaway Recovery', 'Deep Breaths', 'Preferred Position',
        'Groundwork', 'Up-Tempo', 'Unyielding Spirit', 'Pressure', 'Strategist', 'Triple 7s',
        'Shake It Out', 'Intimidate', 'Stamina Eater', 'Intense Gaze', 'Speed Star',
        'Staggering Lead', 'Blinding Flash', 'Restless', 'Trackblazer', 'Meticulous Measures',
        'Keeping the Lead', 'Leader\'s Pride', 'Wait-and-See', 'A Small Breather'
    ],
    [
        # Priority 2 - B Tier skills (Game8 situational but viable)
        'Levelheaded', 'Stop Right There!', 'Super Lucky Seven', 'Maverick ◯', 'Sympathy',
        'Long Shot ◯', 'Inner Post Proficiency ◯', 'Outer Post Proficiency ◯', 'Right-Handed ◯',
        'Left-Handed ◯', 'Firm Conditions ◯', 'Wet Conditions ◯', 'Standard Distance ◯', 
        'Non-Standard Distance ◯', 'Competitive Spirit ◯', 'Target in Sight ◯', 'Lone Wolf'
    ]
]
