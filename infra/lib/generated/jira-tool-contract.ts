// Auto-generated from contracts/jira_tools.contract.json.
// Do not edit by hand; run scripts/generate_tool_contract_artifacts.py.

export const CONTRACT_VERSION = "2.0.0";

export type ContractType = "string" | "array_string";

export interface ContractProperty {
  type: ContractType;
  description?: string;
}

export interface ContractSchema {
  properties: Record<string, ContractProperty>;
  required: string[];
}

export interface GatewayToolContract {
  name: string;
  description: string;
  input_schema: ContractSchema;
  output_schema: ContractSchema;
}

export const MCP_TOOL_SCOPE_BY_INTENT: Record<string, string[]> = {
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
};

export const GATEWAY_TOOLS: GatewayToolContract[] = [
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
        "write_artifact_uri": {
          "type": "string"
        },
        "write_status": {
          "type": "string"
        }
      },
      "required": [
        "key",
        "write_status",
        "write_artifact_uri",
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
];
