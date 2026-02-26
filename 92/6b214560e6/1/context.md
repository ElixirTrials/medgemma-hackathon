# Session Context

## User Prompts

### Prompt 1

Have a look at: instructions/SubmissionRequirements/grounding_failures/gemini_output_caps_and_fixes.md to get an idea of the problems in grounding and extraction that we've already solved. See the image. Then look at the postgres db and MLFlow trace logs for our recent extraction. Any failures should be added to our test json (/Users/noahdolevelixir/Code/medgemma-hackathon/tests/e2e/test_snippets.json) if they are not already there.

### Prompt 2

[Image: source: /Users/noahdolevelixir/Code/medgemma-hackathon/instructions/SubmissionRequirements/grounding_failures/Screenshot 2026-02-26 at 09.52.01.png]

### Prompt 3

Now let's make the following plan: Try our grounding against the new json with 3 prompt variants (including the original) and compare. We want the variant that gets everything right (entities, relations, units, values, etc) for all entries on the json. We want to present our findings to the user at the end of our experiment.

### Prompt 4

[Request interrupted by user for tool use]

