"""JSON schemas for internal Scrabble tools used by AI function calling."""

from __future__ import annotations

from typing import Any

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "rules_first_move_must_cover_center": {
        "name": "rules_first_move_must_cover_center",
        "description": "Check if first move covers center square (7,7)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "placements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row": {"type": "integer", "minimum": 0, "maximum": 14},
                            "col": {"type": "integer", "minimum": 0, "maximum": 14},
                            "letter": {"type": "string", "minLength": 1, "maxLength": 1},
                        },
                        "required": ["row", "col", "letter"],
                    },
                    "description": "List of letter placements",
                }
            },
            "required": ["placements"],
        },
    },
    "rules_placements_in_line": {
        "name": "rules_placements_in_line",
        "description": "Check if all placements are in a single line (ACROSS or DOWN)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "placements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row": {"type": "integer"},
                            "col": {"type": "integer"},
                            "letter": {"type": "string"},
                        },
                        "required": ["row", "col", "letter"],
                    },
                }
            },
            "required": ["placements"],
        },
    },
    "rules_connected_to_existing": {
        "name": "rules_connected_to_existing",
        "description": "Check if placements connect to existing letters on board",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_grid": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 15,
                    "maxItems": 15,
                    "description": "15x15 grid as list of strings ('.' for empty)",
                },
                "placements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row": {"type": "integer"},
                            "col": {"type": "integer"},
                            "letter": {"type": "string"},
                        },
                        "required": ["row", "col", "letter"],
                    },
                },
            },
            "required": ["board_grid", "placements"],
        },
    },
    "rules_no_gaps_in_line": {
        "name": "rules_no_gaps_in_line",
        "description": "Check if there are no gaps in the main line formed by placements",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_grid": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 15,
                    "maxItems": 15,
                },
                "placements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row": {"type": "integer"},
                            "col": {"type": "integer"},
                            "letter": {"type": "string"},
                        },
                    },
                },
                "direction": {
                    "type": "string",
                    "enum": ["ACROSS", "DOWN"],
                    "description": "Direction of the line",
                },
            },
            "required": ["board_grid", "placements", "direction"],
        },
    },
    "rules_extract_all_words": {
        "name": "rules_extract_all_words",
        "description": "Extract all words (main + cross-words) formed by the placements",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_grid": {"type": "array", "items": {"type": "string"}},
                "placements": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
            "required": ["board_grid", "placements"],
        },
    },
    "scoring_score_words": {
        "name": "scoring_score_words",
        "description": "Calculate score for words with premium breakdown",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_grid": {"type": "array", "items": {"type": "string"}},
                "premium_grid": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "used": {"type": "boolean"},
                            },
                            "required": ["type", "used"],
                            "additionalProperties": False,
                        },
                    },
                    "description": "15x15 grid of premium info or null",
                },
                "placements": {"type": "array", "items": {"type": "object"}},
                "words": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "word": {"type": "string"},
                            "cells": {
                                "type": "array",
                                "items": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "minItems": 2,
                                    "maxItems": 2,
                                },
                            },
                        },
                    },
                },
            },
            "required": ["board_grid", "premium_grid", "placements", "words"],
        },
    },
    "get_board_state": {
        "name": "get_board_state",
        "description": "Get current board state as serialized grid",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board": {
                    "type": ["object", "null"],
                    "description": "Board instance (optional, null for empty board)",
                }
            },
        },
    },
    "get_rack_letters": {
        "name": "get_rack_letters",
        "description": "Get available letters on rack",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rack": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of letter strings",
                }
            },
            "required": ["rack"],
        },
    },
    "get_tile_values": {
        "name": "get_tile_values",
        "description": "Get point values for all letters in variant",
        "inputSchema": {
            "type": "object",
            "properties": {
                "variant": {
                    "type": "string",
                    "default": "slovak",
                    "description": "Variant slug (e.g., 'slovak', 'english')",
                }
            },
        },
    },
    "get_premium_squares": {
        "name": "get_premium_squares",
        "description": "Get premium squares on board and whether they are already used",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board": {
                    "type": ["object", "null"],
                    "description": "Board instance (optional, null for default premium layout)",
                }
            },
        },
    },
    "validate_word_slovak": {
        "name": "validate_word_slovak",
        "description": "Validate Slovak word against local dictionary cache and optional online source",
        "inputSchema": {
            "type": "object",
            "properties": {
                "word": {"type": "string", "minLength": 1},
                "use_online": {
                    "type": "boolean",
                    "default": False,
                    "description": "Allow online JULS lookup for long words",
                },
                "retry_count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 2,
                },
                "online_min_length": {
                    "type": ["integer", "null"],
                    "minimum": 2,
                    "maximum": 32,
                    "default": 7,
                },
            },
            "required": ["word"],
        },
    },
    "validate_word_english": {
        "name": "validate_word_english",
        "description": "Validate English word against local TWL/SOWPODS dictionary cache",
        "inputSchema": {
            "type": "object",
            "properties": {
                "word": {"type": "string", "minLength": 1},
                "use_online": {
                    "type": "boolean",
                    "default": False,
                },
            },
            "required": ["word"],
        },
    },
    "validate_move_legality": {
        "name": "validate_move_legality",
        "description": "Validate complete move legality (combines all rule checks)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_grid": {"type": "array", "items": {"type": "string"}},
                "placements": {"type": "array", "items": {"type": "object"}},
                "is_first_move": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether this is the first move",
                },
            },
            "required": ["board_grid", "placements"],
        },
    },
    "calculate_move_score": {
        "name": "calculate_move_score",
        "description": "Calculate total score for a move (extracts words + scores them)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_grid": {"type": "array", "items": {"type": "string"}},
                "premium_grid": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "used": {"type": "boolean"},
                            },
                            "required": ["type", "used"],
                            "additionalProperties": False,
                        },
                    },
                },
                "placements": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["board_grid", "premium_grid", "placements"],
        },
    },
    "get_validation_stats": {
        "name": "get_validation_stats",
        "description": "Get dictionary validation and cache statistics",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
}
