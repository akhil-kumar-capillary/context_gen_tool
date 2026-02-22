# Context Restructuring Blueprint

## Objective
Restructure the provided context documents into a clean, professional, non-conflicting set of context documents that an LLM can efficiently adhere to.

## Rules

### Structure
1. Each output document should have a clear, descriptive name (max 100 chars, alphanumeric + `_:#()-,`)
2. Documents should be organized by topic/domain, not by source
3. Remove all duplicate information across documents
4. Resolve any conflicting instructions — prefer the most specific/recent version

### Content Quality
1. Use markdown formatting for all content
2. Write in imperative/instructional tone (rules the LLM must follow)
3. Be precise and unambiguous — avoid vague language
4. Include concrete examples where helpful
5. Group related rules together under clear headings

### Token Efficiency
1. Remove filler words and redundant phrases
2. Use tables for structured data (column descriptions, code mappings)
3. Use bullet points for lists of rules
4. Avoid repeating context that can be cross-referenced

### Output Format
Return a JSON array where each element has:
- `name`: Document name (string, max 100 chars)
- `content`: Document content (string, markdown formatted)

```json
[
  {"name": "document_name", "content": "# Document Title\n\nContent here..."},
  ...
]
```

## Budget
Distribute content across documents proportionally. Each document should target approximately {per_doc_budget} tokens of output.
