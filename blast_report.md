# Blast Radius Report

## Change Summary
- Change Type: `function_logic_change`
- Target: `function:services.user_service.create_user`
- Modification: `adjust validation flow`

## Direct Impacts
- `class:models.user_model.User` (Data Handling): Immediate dependency/caller path: create_user -> User
- `function:api.user_api.post_user` (API-Level): Immediate dependency/caller path: post_user -> create_user
- `function:database.db.save_user` (Business Logic): Immediate dependency/caller path: create_user -> save_user
- `function:utils.validation.validate_user` (Business Logic): Immediate dependency/caller path: create_user -> validate_user

## Indirect Impacts
- `data:request.get` (Data Handling): Transitive dependency path: create_user -> post_user -> request.get
- `data:user.username` (Data Handling): Transitive dependency path: create_user -> save_user -> user.username
- `external:print` (Business Logic): Transitive dependency path: create_user -> save_user -> print
- `external:request.get` (Business Logic): Transitive dependency path: create_user -> post_user -> request.get

## Risk Zones
- Unknown Impact Zone: unresolved symbols or dynamic behavior detected.
- Unknown test coverage for impacted components.

## Severity: High
