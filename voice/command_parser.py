"""
Voice command parser.
Converts speech transcripts into structured robot commands.
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Import waypoints for landmark navigation
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from constants import FACTORY_WAYPOINTS


@dataclass
class ParsedCommand:
    """Structured command extracted from a voice transcript."""
    command_type: str       # "direct_override" or "automated"
    action: str             # "STOP", "NAVIGATE", "TRANSPORT", etc.
    robot_id: str | None = None
    target: str | None = None
    item: str | None = None
    stack_id: str | None = None
    raw_text: str = ""
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class CommandSequence:
    """A sequence of commands parsed from a compound voice instruction."""
    steps: list[ParsedCommand]
    raw_text: str = ""
    confidence: float = 1.0


# Direct override commands — keyword -> action
_DIRECT_COMMANDS: list[tuple[list[str], str]] = [
    (["emergency stop"], "EMERGENCY_STOP"),
    (["stop all"], "STOP_ALL"),
    (["cancel navigation", "cancel nav", "abort navigation", "stop navigating"], "CANCEL_NAV"),
    (["stop", "halt"], "STOP"),
    (["move forward", "go forward"], "FORWARD"),
    (["move back", "move backward", "reverse", "go back"], "BACKWARD"),
    (["turn left", "rotate left", "go left"], "LEFT"),
    (["turn right", "rotate right", "go right"], "RIGHT"),
    (["grab", "pick up", "grasp"], "GRAB"),
    (["release", "drop", "let go"], "RELEASE"),
    (["shift gear", "change gear", "next gear"], "SHIFT_GEAR"),
    (["set gear forward", "gear forward"], "SET_GEAR_FORWARD"),
    (["set gear reverse", "gear reverse"], "SET_GEAR_REVERSE"),
    (["set gear neutral", "gear neutral"], "SET_GEAR_NEUTRAL"),
]

# Navigation verb prefixes — checked before landmark matching
_NAV_VERBS = [
    "walk to", "walk over to",
    "go to", "go over to",
    "navigate to",
    "move to", "move over to",
    "head to", "head over to",
    "drive to",
    "take me to",
    "bring me to",
]

# Landmark aliases → canonical FACTORY_WAYPOINTS name
_LANDMARK_ALIASES: dict[str, str] = {
    "shelf a": "Shelf A",
    "shelf 1": "Shelf A",
    "shelve a": "Shelf A",
    "shelf b": "Shelf B",
    "shelf 2": "Shelf B",
    "shelve b": "Shelf B",
    "conveyor": "Conveyor",
    "conveyor belt": "Conveyor",
    "the conveyor": "Conveyor",
    "belt": "Conveyor",
    "table": "Table",
    "the table": "Table",
    "work table": "Table",
    "pallet 1": "Pallet 1",
    "pallet one": "Pallet 1",
    "source pallet": "Pallet 1",
    "first pallet": "Pallet 1",
    "palette 1": "Pallet 1",
    "palette one": "Pallet 1",
    "pallet 2": "Pallet 2",
    "pallet two": "Pallet 2",
    "destination pallet": "Pallet 2",
    "second pallet": "Pallet 2",
    "palette 2": "Pallet 2",
    "palette two": "Pallet 2",
    "pallet": "Pallet 2",
    "palette": "Pallet 2",
    "the pallet": "Pallet 2",
    "the palette": "Pallet 2",
    "pallet to": "Pallet 2",
    "palette to": "Pallet 2",
    "shelf to": "Shelf B",
    "shelve to": "Shelf B",
}

# Regex patterns for extracting entities
_ROBOT_ID_PATTERN = re.compile(r'\b[Rr](?:obot\s*)?(\d+)\b')
_ZONE_PATTERN = re.compile(r'\bzone\s+([A-Za-z]\d+)\b', re.IGNORECASE)
_BOX_PATTERN = re.compile(r'\bbox\s+([A-Za-z]?\d+)\b', re.IGNORECASE)
_STACK_PATTERN = re.compile(r'\bstack\s+([A-Za-z]?\d+)\b', re.IGNORECASE)

# Automated command templates — (keywords, action)
_AUTO_TEMPLATES: list[tuple[list[str], str]] = [
    (["bring", "transport", "carry", "deliver"], "TRANSPORT"),
    (["move to", "go to", "navigate to", "head to"], "NAVIGATE"),
    (["pick up", "grab", "get"], "PICKUP"),
    (["override", "take control", "manual control"], "OVERRIDE"),
]

# Conjunction words that split compound commands
_CONJUNCTIONS = re.compile(r'\b(?:and then|then|and|after that|afterwards)\b')

# Compound template patterns:
#   "take/bring/carry [the] [box/object/item] from <A> to <B>"
#   "fetch [the] [box] from <A> to <B>"
#   "move [the] [box] from <A> to <B>"
_TRANSPORT_PATTERN = re.compile(
    r'(?:take|bring|carry|fetch|move|deliver|transport)\s+'
    r'(?:the\s+)?(?:box|object|item|package|thing)?\s*'
    r'(?:from\s+)?(.+?)\s+to\s+(.+)',
    re.IGNORECASE,
)

# "pick up [the] [box] at/from <A> and bring/take it to <B>"
_PICKUP_DELIVER_PATTERN = re.compile(
    r'(?:pick up|grab|get)\s+(?:the\s+)?(?:box|object|item|package|thing)?\s*'
    r'(?:at|from|near)?\s*(.+?)\s+'
    r'(?:and\s+)?(?:bring|take|carry|deliver|move)\s+(?:it\s+)?to\s+(.+)',
    re.IGNORECASE,
)

# Action keywords for post-navigation actions
_POST_NAV_ACTIONS = {
    "grab": "GRAB", "pick up": "GRAB", "grasp": "GRAB", "get": "GRAB",
    "release": "RELEASE", "drop": "RELEASE", "put down": "RELEASE",
    "let go": "RELEASE", "place": "RELEASE", "deliver": "RELEASE",
}


def _resolve_landmark(text: str) -> str | None:
    """Try to find a landmark name in the text. Returns canonical name or None."""
    # Exact alias match
    if text in _LANDMARK_ALIASES:
        return _LANDMARK_ALIASES[text]

    # Check if any alias is a substring
    for alias, canonical in sorted(_LANDMARK_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in text:
            return canonical

    # Check against waypoint names directly
    for wp_name in FACTORY_WAYPOINTS:
        if wp_name.lower() in text:
            return wp_name

    return None


class CommandParser:
    """Parses voice transcripts into structured commands."""

    def parse_sequence(self, transcript: str, confidence: float = 1.0) -> CommandSequence | None:
        """
        Parse a voice transcript into a sequence of commands.

        Handles compound instructions like:
          - "Go to shelf A and grab the box"          → [NAVIGATE(Shelf A), GRAB]
          - "Take the box from the conveyor to pallet 2" → [NAV(Conveyor), GRAB, NAV(Pallet 2), RELEASE]
          - "Pick up the box and bring it to the table"  → [GRAB, NAV(Table), RELEASE]
          - "Move to shelf B then release"              → [NAVIGATE(Shelf B), RELEASE]

        Returns None if nothing matches, or a CommandSequence with 1+ steps.
        Falls back to single-command parse() for simple instructions.
        """
        if not transcript or not transcript.strip():
            return None
        text = transcript.strip().lower()

        # --- Try compound templates first (highest priority) ---

        # "take/bring the box from <A> to <B>"  →  nav(A) + grab + nav(B) + release
        m = _TRANSPORT_PATTERN.match(text)
        if m:
            src_text, dst_text = m.group(1).strip(), m.group(2).strip()
            # Strip trailing filler like "the" from destination
            for filler in ("the ", "a "):
                if src_text.startswith(filler):
                    src_text = src_text[len(filler):]
                if dst_text.startswith(filler):
                    dst_text = dst_text[len(filler):]
            src = _resolve_landmark(src_text)
            dst = _resolve_landmark(dst_text)
            if src and dst:
                return CommandSequence(
                    steps=[
                        ParsedCommand(command_type="automated", action="NAVIGATE", target=src),
                        ParsedCommand(command_type="automated", action="GRAB"),
                        ParsedCommand(command_type="automated", action="NAVIGATE", target=dst),
                        ParsedCommand(command_type="automated", action="RELEASE"),
                    ],
                    raw_text=transcript,
                    confidence=confidence,
                )

        # "pick up the box at <A> and bring it to <B>"
        m = _PICKUP_DELIVER_PATTERN.match(text)
        if m:
            src_text, dst_text = m.group(1).strip(), m.group(2).strip()
            for filler in ("the ", "a "):
                if src_text.startswith(filler):
                    src_text = src_text[len(filler):]
                if dst_text.startswith(filler):
                    dst_text = dst_text[len(filler):]
            src = _resolve_landmark(src_text)
            dst = _resolve_landmark(dst_text)
            if src and dst:
                return CommandSequence(
                    steps=[
                        ParsedCommand(command_type="automated", action="NAVIGATE", target=src),
                        ParsedCommand(command_type="automated", action="GRAB"),
                        ParsedCommand(command_type="automated", action="NAVIGATE", target=dst),
                        ParsedCommand(command_type="automated", action="RELEASE"),
                    ],
                    raw_text=transcript,
                    confidence=confidence,
                )

        # --- Try conjunction splitting: "go to X and grab the box" ---
        parts = _CONJUNCTIONS.split(text)
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) > 1:
            steps = []
            for part in parts:
                cmd = self._parse_fragment(part)
                if cmd:
                    steps.append(cmd)
            if steps:
                return CommandSequence(
                    steps=steps, raw_text=transcript, confidence=confidence,
                )

        # --- Fallback: single command wrapped as a 1-step sequence ---
        single = self.parse(transcript, confidence)
        if single:
            return CommandSequence(
                steps=[single], raw_text=transcript, confidence=confidence,
            )

        return None

    def _parse_fragment(self, text: str) -> ParsedCommand | None:
        """Parse a single fragment from a split compound sentence."""
        text = text.strip()
        # Strip leading filler
        for filler in ("then ", "also ", "please "):
            if text.startswith(filler):
                text = text[len(filler):]

        # Navigation fragment: "go to shelf A"
        cmd = self._match_navigation(text)
        if cmd:
            return cmd

        # Post-nav action fragment: "grab the box", "release it", "pick up the object"
        for keyword, action in _POST_NAV_ACTIONS.items():
            if keyword in text:
                return ParsedCommand(command_type="automated", action=action)

        # Direct command fragment: "stop", "move forward"
        cmd = self._match_direct(text)
        if cmd:
            return cmd

        # Try to find just a landmark name (implicit navigate)
        landmark = _resolve_landmark(text)
        if landmark:
            return ParsedCommand(command_type="automated", action="NAVIGATE", target=landmark)

        return None

    def parse(self, transcript: str, confidence: float = 1.0) -> ParsedCommand | None:
        """
        Parse a voice transcript into a structured command.
        Returns None if the transcript doesn't match any known pattern.
        """
        if not transcript or not transcript.strip():
            return None

        text = transcript.strip().lower()

        # Try landmark navigation first (before direct, so "walk to shelf B"
        # doesn't match "walk" → FORWARD)
        cmd = self._match_navigation(text)
        if cmd:
            cmd.raw_text = transcript
            cmd.confidence = confidence
            return cmd

        # Try direct override
        cmd = self._match_direct(text)
        if cmd:
            cmd.raw_text = transcript
            cmd.confidence = confidence
            return cmd

        # Try automated/strategic commands (need robot ID or zone)
        cmd = self._match_automated(text)
        if cmd:
            cmd.raw_text = transcript
            cmd.confidence = confidence
            return cmd

        return None

    def _match_navigation(self, text: str) -> ParsedCommand | None:
        """Match 'walk to shelf B' style navigation commands."""
        for verb in _NAV_VERBS:
            if verb in text:
                # Extract everything after the verb as the landmark
                remainder = text.split(verb, 1)[1].strip()
                # Strip leading "the "
                if remainder.startswith("the "):
                    remainder = remainder[4:]
                landmark = _resolve_landmark(remainder)
                if landmark:
                    return ParsedCommand(
                        command_type="automated",
                        action="NAVIGATE",
                        target=landmark,
                    )

        # Also try without verb: just "shelf B" or "conveyor" alone won't trigger
        # to avoid false positives. But "walk shelf B" should work.
        return None

    def _match_direct(self, text: str) -> ParsedCommand | None:
        """Match against direct override keyword list."""
        for keywords, action in _DIRECT_COMMANDS:
            for kw in keywords:
                if kw in text:
                    return ParsedCommand(
                        command_type="direct_override",
                        action=action,
                    )
        return None

    def _match_automated(self, text: str) -> ParsedCommand | None:
        """Match automated commands with entity extraction."""
        robot_match = _ROBOT_ID_PATTERN.search(text)
        zone_match = _ZONE_PATTERN.search(text)
        box_match = _BOX_PATTERN.search(text)
        stack_match = _STACK_PATTERN.search(text)

        robot_id = f"R{robot_match.group(1)}" if robot_match else None
        target = f"zone_{zone_match.group(1).upper()}" if zone_match else None
        item = f"box_{box_match.group(1)}" if box_match else None
        stack_id = f"stack_{stack_match.group(1)}" if stack_match else None

        # Need at least a robot ID or a zone to consider this automated
        if not robot_id and not target:
            return None

        # Match action template
        action = "NAVIGATE"  # default if robot + zone but no verb
        for keywords, act in _AUTO_TEMPLATES:
            for kw in keywords:
                if kw in text:
                    action = act
                    break

        # Refine: if we have an item and a target, it's TRANSPORT
        if item and target:
            action = "TRANSPORT"

        return ParsedCommand(
            command_type="automated",
            action=action,
            robot_id=robot_id,
            target=target,
            item=item,
            stack_id=stack_id,
        )