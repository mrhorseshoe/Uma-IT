"""Enumerations the app shares.

Only the scenarios an Independent Training run can be started in. The values
match the parent project's ScenarioType so a task saved there restores here
without translation.
"""
from enum import Enum


class ScenarioType(Enum):
    UNKNOWN = 0
    URA = 1
    AOHARUHAI = 2
    TRACKBLAZER = 3
    GRAND_CONCERT = 4
