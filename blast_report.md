# Blast Radius Report

## Change Summary
- Change Type: `function_logic_change`
- Target: `function:services.user_service.create_user`
- Modification: `adjust validation flow`

## Direct Impacts
- `class:models.user_model.User` (Data Handling): Impact propagates via relations [DEPENDS_ON] along path: create_user -> User
- `function:api.user_api.post_user` (API-Level): Impact propagates via relations [CALLS] along path: create_user -> post_user
- `function:database.db.save_user` (Business Logic): Impact propagates via relations [CALLS] along path: create_user -> save_user
- `function:utils.validation.validate_user` (Business Logic): Impact propagates via relations [CALLS] along path: create_user -> validate_user

## Indirect Impacts
- `data:self.age` (Data Handling): Impact propagates via relations [DEPENDS_ON -> WRITES] along path: create_user -> User -> self.age
- `data:self.username` (Data Handling): Impact propagates via relations [DEPENDS_ON -> WRITES] along path: create_user -> User -> self.username
- `data:user.username` (Data Handling): Impact propagates via relations [CALLS -> READS] along path: create_user -> save_user -> user.username
- `function:models.user_model.User.__init__` (Business Logic): Impact propagates via relations [DEPENDS_ON -> DEPENDS_ON] along path: create_user -> User -> __init__

## Risk Zones
- Unknown Impact Zone: unresolved symbols or dynamic behavior detected.
- Unknown test coverage for impacted components.

## Severity: High
