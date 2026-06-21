# Priority Email Evolution

This package keeps the Priority Email project chronology readable as both narrative and generated flow diagrams.

## Reading Path

1. Start with [../../EVOLUTION.md](../../EVOLUTION.md) for the full project chronology.
2. Use the category files for focused history:
   - [categories/product-requirements.md](categories/product-requirements.md)
   - [categories/deployment-operations.md](categories/deployment-operations.md)
   - [categories/agent-policy-safety.md](categories/agent-policy-safety.md)
3. Use the generated diagrams when a visual project flow is easier to scan.

## Generated Diagrams

- [diagrams/priority-email-evolution-flow.dot](diagrams/priority-email-evolution-flow.dot)
- [diagrams/priority-email-evolution-flow.svg](diagrams/priority-email-evolution-flow.svg)
- [diagrams/priority-email-evolution-flow.png](diagrams/priority-email-evolution-flow.png)
- [diagrams/priority-email-evolution-flow-dark.dot](diagrams/priority-email-evolution-flow-dark.dot)
- [diagrams/priority-email-evolution-flow-dark.svg](diagrams/priority-email-evolution-flow-dark.svg)
- [diagrams/priority-email-evolution-flow-dark.png](diagrams/priority-email-evolution-flow-dark.png)

## Regeneration

```bash
dot -Tsvg docs/evolution/diagrams/priority-email-evolution-flow.dot -o docs/evolution/diagrams/priority-email-evolution-flow.svg
dot -Tpng docs/evolution/diagrams/priority-email-evolution-flow.dot -o docs/evolution/diagrams/priority-email-evolution-flow.png
dot -Tsvg docs/evolution/diagrams/priority-email-evolution-flow-dark.dot -o docs/evolution/diagrams/priority-email-evolution-flow-dark.svg
dot -Tpng docs/evolution/diagrams/priority-email-evolution-flow-dark.dot -o docs/evolution/diagrams/priority-email-evolution-flow-dark.png
```
