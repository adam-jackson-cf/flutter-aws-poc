# Auto-generated from contracts/jira_tools.contract.json.
# Do not edit by hand; run scripts/generate_tool_contract_artifacts.py.

INTENT_KEYWORDS = {
    "bug_triage": [
        "bug",
        "incident",
        "error",
        "outage",
        "failure",
        "broken"
    ],
    "feature_request": [
        "feature",
        "suggestion",
        "roadmap",
        "improvement"
    ],
    "status_update": [
        "status",
        "progress",
        "update",
        "latest"
    ]
}

RISK_HINT_TOKENS = [
    "accessibility",
    "security",
    "compliance",
    "customer",
    "incident",
    "escalation"
]

MCP_EXPECTED_TOOL = "jira_get_issue_by_key"
NATIVE_EXPECTED_TOOL = "jira_api_get_issue_by_key"

MCP_TOOL_SCOPE_BY_INTENT = {
    "bug_triage": [
        "jira_get_issue_by_key",
        "jira_get_issue_priority_context",
        "jira_get_issue_status_snapshot",
        "jira_write_issue_followup_note"
    ],
    "feature_request": [
        "jira_get_issue_by_key",
        "jira_get_issue_labels",
        "jira_get_issue_project_key"
    ],
    "general_triage": [
        "jira_get_issue_by_key",
        "jira_get_issue_status_snapshot"
    ],
    "status_update": [
        "jira_get_issue_by_key",
        "jira_get_issue_status_snapshot",
        "jira_get_issue_update_timestamp"
    ]
}

NATIVE_TOOL_SCOPE_BY_INTENT = {
    "bug_triage": [
        "jira_api_get_issue_by_key",
        "jira_api_get_issue_priority_context",
        "jira_api_get_issue_status_snapshot",
        "jira_api_write_issue_followup_note"
    ],
    "feature_request": [
        "jira_api_get_issue_by_key",
        "jira_api_get_issue_labels",
        "jira_api_get_issue_project_key"
    ],
    "general_triage": [
        "jira_api_get_issue_by_key",
        "jira_api_get_issue_status_snapshot"
    ],
    "status_update": [
        "jira_api_get_issue_by_key",
        "jira_api_get_issue_status_snapshot",
        "jira_api_get_issue_update_timestamp"
    ]
}

NATIVE_TOOL_DESCRIPTIONS = {
    "jira_api_get_issue_by_key": "Fetch complete issue payload from Jira REST API by issue key.",
    "jira_api_get_issue_labels": "Fetch issue labels for classification context.",
    "jira_api_get_issue_priority_context": "Fetch issue priority and derived risk band from Jira.",
    "jira_api_get_issue_project_key": "Fetch project key derived from issue key.",
    "jira_api_get_issue_status_snapshot": "Fetch status and update timestamp for an issue key.",
    "jira_api_get_issue_update_timestamp": "Fetch issue update timestamp for freshness checks.",
    "jira_api_write_issue_followup_note": "Persist a customer follow-up note artifact for an issue."
}

TOOL_COMPLETENESS_FIELDS_BY_OPERATION = {
    "get_issue_by_key": [
        "key",
        "summary",
        "status"
    ],
    "get_issue_labels": [
        "key",
        "labels"
    ],
    "get_issue_priority_context": [
        "key",
        "priority"
    ],
    "get_issue_project_key": [
        "key",
        "project_key"
    ],
    "get_issue_risk_flags": [
        "key"
    ],
    "get_issue_status_snapshot": [
        "key",
        "status",
        "updated"
    ],
    "get_issue_update_timestamp": [
        "key",
        "updated"
    ],
    "write_issue_followup_note": [
        "key",
        "write_status",
        "write_artifact_s3_uri"
    ]
}

GATEWAY_TOOLS = [
    {
        "description": "Fetch a public Jira issue by key, including summary, status, priority and labels.",
        "input_schema": {
            "properties": {
                "issue_key": {
                    "description": "Issue key such as JRASERVER-79286",
                    "type": "string"
                }
            },
            "required": [
                "issue_key"
            ]
        },
        "name": "jira_get_issue_by_key",
        "output_schema": {
            "properties": {
                "key": {
                    "type": "string"
                },
                "status": {
                    "type": "string"
                },
                "summary": {
                    "type": "string"
                }
            },
            "required": [
                "key",
                "summary",
                "status"
            ]
        }
    },
    {
        "description": "Get current status and update timestamp for an issue.",
        "input_schema": {
            "properties": {
                "issue_key": {
                    "description": "Issue key such as JRASERVER-79286",
                    "type": "string"
                }
            },
            "required": [
                "issue_key"
            ]
        },
        "name": "jira_get_issue_status_snapshot",
        "output_schema": {
            "properties": {
                "key": {
                    "type": "string"
                },
                "status": {
                    "type": "string"
                },
                "updated": {
                    "type": "string"
                }
            },
            "required": [
                "key",
                "status",
                "updated"
            ]
        }
    },
    {
        "description": "Get issue priority and derived risk band.",
        "input_schema": {
            "properties": {
                "issue_key": {
                    "description": "Issue key such as JRASERVER-79286",
                    "type": "string"
                }
            },
            "required": [
                "issue_key"
            ]
        },
        "name": "jira_get_issue_priority_context",
        "output_schema": {
            "properties": {
                "key": {
                    "type": "string"
                },
                "priority": {
                    "type": "string"
                },
                "risk_band": {
                    "type": "string"
                }
            },
            "required": [
                "key",
                "priority",
                "risk_band"
            ]
        }
    },
    {
        "description": "Get labels attached to an issue.",
        "input_schema": {
            "properties": {
                "issue_key": {
                    "description": "Issue key such as JRASERVER-79286",
                    "type": "string"
                }
            },
            "required": [
                "issue_key"
            ]
        },
        "name": "jira_get_issue_labels",
        "output_schema": {
            "properties": {
                "key": {
                    "type": "string"
                },
                "labels": {
                    "type": "array_string"
                }
            },
            "required": [
                "key",
                "labels"
            ]
        }
    },
    {
        "description": "Get the Jira project key extracted from an issue key.",
        "input_schema": {
            "properties": {
                "issue_key": {
                    "description": "Issue key such as JRASERVER-79286",
                    "type": "string"
                }
            },
            "required": [
                "issue_key"
            ]
        },
        "name": "jira_get_issue_project_key",
        "output_schema": {
            "properties": {
                "key": {
                    "type": "string"
                },
                "project_key": {
                    "type": "string"
                }
            },
            "required": [
                "key",
                "project_key"
            ]
        }
    },
    {
        "description": "Get the most recent update timestamp for an issue.",
        "input_schema": {
            "properties": {
                "issue_key": {
                    "description": "Issue key such as JRASERVER-79286",
                    "type": "string"
                }
            },
            "required": [
                "issue_key"
            ]
        },
        "name": "jira_get_issue_update_timestamp",
        "output_schema": {
            "properties": {
                "key": {
                    "type": "string"
                },
                "updated": {
                    "type": "string"
                }
            },
            "required": [
                "key",
                "updated"
            ]
        }
    },
    {
        "description": "Persist a customer follow-up note artifact for an issue key.",
        "input_schema": {
            "properties": {
                "issue_key": {
                    "description": "Issue key such as JRASERVER-79286",
                    "type": "string"
                },
                "note_text": {
                    "description": "Customer-safe note text to persist.",
                    "type": "string"
                }
            },
            "required": [
                "issue_key",
                "note_text"
            ]
        },
        "name": "jira_write_issue_followup_note",
        "output_schema": {
            "properties": {
                "key": {
                    "type": "string"
                },
                "note_digest": {
                    "type": "string"
                },
                "write_artifact_s3_uri": {
                    "type": "string"
                },
                "write_status": {
                    "type": "string"
                }
            },
            "required": [
                "key",
                "write_status",
                "write_artifact_s3_uri",
                "note_digest"
            ]
        }
    },
    {
        "description": "Get risk-related flags derived from issue labels.",
        "input_schema": {
            "properties": {
                "issue_key": {
                    "description": "Issue key such as JRASERVER-79286",
                    "type": "string"
                }
            },
            "required": [
                "issue_key"
            ]
        },
        "name": "jira_get_issue_risk_flags",
        "output_schema": {
            "properties": {
                "key": {
                    "type": "string"
                },
                "risk_flags": {
                    "type": "array_string"
                }
            },
            "required": [
                "key",
                "risk_flags"
            ]
        }
    },
    {
        "description": "Get a sentiment signal for customer communication readiness.",
        "input_schema": {
            "properties": {
                "issue_key": {
                    "description": "Issue key such as JRASERVER-79286",
                    "type": "string"
                }
            },
            "required": [
                "issue_key"
            ]
        },
        "name": "jira_get_customer_sentiment",
        "output_schema": {
            "properties": {
                "key": {
                    "type": "string"
                },
                "sentiment": {
                    "type": "string"
                },
                "status": {
                    "type": "string"
                }
            },
            "required": [
                "key",
                "sentiment",
                "status"
            ]
        }
    },
    {
        "description": "Get a short message seed based on the issue summary.",
        "input_schema": {
            "properties": {
                "issue_key": {
                    "description": "Issue key such as JRASERVER-79286",
                    "type": "string"
                }
            },
            "required": [
                "issue_key"
            ]
        },
        "name": "jira_get_issue_customer_message_seed",
        "output_schema": {
            "properties": {
                "key": {
                    "type": "string"
                },
                "seed_message": {
                    "type": "string"
                }
            },
            "required": [
                "key",
                "seed_message"
            ]
        }
    }
]
