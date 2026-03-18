# BPMN XML Generator

AI-powered BPMN diagram XML generator that converts natural language process descriptions into valid Camunda 8 BPMN XML.

## Features

- **Natural Language Processing**: Converts plain English process descriptions into BPMN XML
- **Camunda 8 Compatible**: Generates XML with proper Zeebe extensions
- **Multiple Element Types**: Supports start events, end events, user tasks, service tasks, and gateways
- **Valid BPMN 2.0**: Produces standards-compliant BPMN XML
- **No Dependencies**: Uses only Python standard library

## Quick Start

```bash
python bpmn_generator.py
```

## Usage Examples

### Simple Process
Input: "Start the process. User approves request. Send email notification. End process."

Output: Valid BPMN XML with start event → user task → service task → end event

### Complex Process
Input: "Begin order processing. Check if payment is valid. If valid, process order and send confirmation. If invalid, notify user and end. Complete process."

Output: BPMN XML with exclusive gateway and conditional flows

## Supported Elements

- **Start Events**: Keywords: start, begin, initiate
- **End Events**: Keywords: end, finish, complete, terminate  
- **User Tasks**: Keywords: user, manual, human, approve, review
- **Service Tasks**: Keywords: service, system, automated, process, calculate, send, email
- **Exclusive Gateways**: Keywords: decision, choice, gateway, if, condition

## Generated XML Structure

The generator produces complete BPMN XML including:
- Proper namespace declarations
- Camunda 8 Zeebe extensions
- Sequence flows connecting elements
- Optional diagram layout information

## Example Output

```xml
<?xml version="1.0" ?>
<bpmn:definitions exporter="BPMN Generator" exporterVersion="1.0.0" ...>
  <bpmn:process id="Process_12345678" name="Generated Process" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" name="Start the process">
      <bpmn:outgoing>Flow_1</bpmn:outgoing>
    </bpmn:startEvent>
    <!-- More elements... -->
  </bpmn:process>
</bpmn:definitions>
```

## Customization

The parser can be extended to:
- Add more element types (call activities, subprocesses, etc.)
- Integrate with LLM APIs for better natural language understanding
- Add business rules and conditional logic
- Include more sophisticated diagram layout

## Requirements

- Python 3.7+
- No external dependencies (uses standard library only)

## License

MIT
