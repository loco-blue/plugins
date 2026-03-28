# groq

A node plugin for Loco

## Overview

**Type:** node  
**Version:** 0.1.0  
**Author:** loco

## Installation

Install the plugin package through Loco's plugin management system. See Loco documentation for details.

## Architecture

This plugin uses the **NodePlugin** base class, which provides a simple interface for sandbox execution:

```python
class GroqNode(NodePlugin):
    async def execute(
        self,
        inputs: dict[str, Any],    # Input values from config
        context: dict[str, Any]    # Workflow context
    ) -> dict[str, Any]:           # Output values
        # Your logic here
        return {"output": result}
```

**Key Benefits:**
- ✅ Simple interface - no workflow engine dependencies
- ✅ Easy to test standalone
- ✅ Compatible with distributed mode
- ✅ Runs in isolated sandbox environment

### Execution Flow

```
Workflow Engine → PluginNode (proxy) → SandboxService → GroqNode.execute()
```

The plugin code runs on the sandbox server in an isolated environment with its own dependencies.

## Usage

### Configuration

Configure in `plugin.yaml`:

```yaml
config_schema:
  - name: api_key
    type: secret
    required: true
```

### Node Definition

The node is defined in `nodes/groq.yaml`:

```yaml
name: groq
source: nodes/groq.py  # Path to NodePlugin class
inputs:
  - name: input
    type: string
    required: true
outputs:
  - name: output
    type: string
```

### Example in Workflow

```yaml
nodes:
  my_node:
    type: plugin
    config:
      plugin_name: groq
      plugin_version: "0.1.0"
      node_name: groq
      input: "{{start.data}}"```

**Direct Usage (Testing):**

```python
from nodes.groq import GroqNode

# Initialize
node = GroqNode()
await node.initialize()

# Execute
result = await node.execute(
    inputs={"input": "your data"},
    context={"execution_id": "test-123"}
)
print(result["output"])

# Cleanup
await node.cleanup()
```

## Inputs

| Name | Type | Required | Description |
|------|------|----------|-------------|
| input | string | Yes | Data to process |

## Outputs

| Name | Type | Description |
|------|------|-------------|
| output | string | Processed data |
| status | string | Execution status |

## Development

### Setup

Dependencies are managed in `plugin.yaml`. The Loco system automatically installs them when the plugin is loaded.

### Testing

```bash
loco plugin test .
```

### Building

```bash
loco cli plugin build .
```

## License

MIT

## Support

- Issues: https://github.com/your-org/loco/issues
- Docs: https://docs.loco.dev/plugins