# Pull Request Template

## Description

Please include a summary of the change and which issue is fixed. Include the motivation and context, and list any dependencies that are required for this change.

Fixes # (issue number)

## Type of change

Please delete options that are not relevant.

-   [ ] Bug fix (non-breaking change which fixes an issue)
-   [ ] New feature (non-breaking change which adds functionality)
-   [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
-   [ ] This change requires a documentation update

## How Has This Been Tested?

Please describe the tests that you ran to verify your changes. Provide instructions so we can reproduce. Please also list any relevant details for your test configuration.

-   [ ] Test A
-   [ ] Test B

## Manual GPU and Real-Data Validation

GitHub-hosted CI does not have enough disk or GPU access to validate the full
ROS/CUDA runtime. Complete every applicable check below before requesting a
merge. If a check is not affected by this PR, leave it unchecked and explain
why under **Not applicable**.

### Test environment

- Tester:
- OS:
- GPU and VRAM:
- NVIDIA driver:
- Docker image or commit tested:
- Test data used (do not link confidential data):

### Manual checks

- [ ] Docker Compose starts the frontend and backend without errors
- [ ] CUDA is detected inside the backend container
- [ ] PyTorch reports CUDA as available and identifies the expected GPU
- [ ] A representative image is processed successfully on the GPU
- [ ] A representative video is processed successfully on the GPU
- [ ] Whisper/audio processing completes successfully, when affected
- [ ] ROSBag processing completes from upload/input through final output
- [ ] Generated annotations and frontend playback/timeline output were inspected
- [ ] No API keys, `.env` files, ROS bags, images, videos, or generated private data are included in the commit or image layer

### Evidence

Provide a short result summary and attach non-sensitive screenshots or log
excerpts where useful. Never paste API keys or confidential source data.

- Result:
- Evidence:
- Known limitations:

### Not applicable

List each unchecked item and explain why the change cannot affect it.

## Dependencies

Mention any dependencies this PR relies on or blocks

Depends on # (PR)
Blocks # (PR)

## Screenshots/Documentation

Include any relevant screenshots or gifs that demonstrate the UI changes. Include links to updated documentation if applicable.

## Checklist for Reviewers

-   [ ] Code follows the project's style guidelines
-   [ ] Adequate tests have been added
-   [ ] Functionality and bug fixes are confirmed via tests
-   [ ] Existing tests have been adapted to accommodate the changes
-   [ ] The changes do not generate new warnings/errors

## Request for Specific Feedback

Optional: Mention any particular aspects of the PR where you would like to receive specific feedback.

## Additional Information

Anything else you want to add (links to documentation, style guides, etc.)
