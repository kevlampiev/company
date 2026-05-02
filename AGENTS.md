# AGENTS.md - Development Guidelines

## Project Overview
This is a Node.js/TypeScript project. Source code resides in `src/` and tests in `**/*.test.ts` files adjacent to source files.

## Build & Development Commands

```bash
# Install dependencies
npm install

# Build the project
npm run build

# Run all tests
npm test

# Run a single test file
npm run test:single -- path/to/test.test.ts

# Run a single test by name pattern
npm run test:single -- -t "test name pattern"

# Lint all source files
npm run lint

# Auto-fix linting issues
npm run lint:fix

# Type checking (without emitting files)
npm run typecheck
```

## Code Style Guidelines

### Imports
- Use ES module syntax (`import/export`) over CommonJS
- Group imports in this order, separated by blank lines:
  1. Node.js built-in modules
  2. External packages
  3. Internal modules (absolute imports from `src/`)
  4. Relative imports (`./` and `../`)
- Sort imports alphabetically within each group
- Prefer named imports over default imports when possible
- Use absolute imports for internal modules: `import { foo } from 'src/utils'` not `from '../../utils'`

```typescript
import { readFile } from 'fs/promises';
import { z } from 'zod';
import { formatDate } from 'src/utils/date';
import { helper } from './helper';
```

### Formatting
- Use 2 spaces for indentation
- Use single quotes for strings, except when escaping is needed
- Semicolons are required at end of statements
- Trailing commas in multiline objects/arrays
- Max line length: 100 characters (soft limit)
- Use LF (`\n`) line endings, not CRLF

### Types & TypeScript
- Enable strict mode (already in tsconfig.json)
- Explicitly type function parameters and return types
- Use `interface` for object shapes that will be extended, `type` for unions/intersections
- Avoid `any` - use `unknown` if type is truly unknown
- Use type guards instead of type assertions when possible
- Prefer `as const` for readonly tuples and literal types

```typescript
interface User {
  id: string;
  name: string;
}

type Status = 'active' | 'inactive' | 'suspended';

function getUser(id: string): Promise<User> {
  return fetchUser(id);
}
```

### Naming Conventions
- **Variables/functions**: camelCase (`userName`, `calculateTotal`)
- **Constants**: UPPER_SNAKE_CASE (`MAX_RETRIES`, `API_URL`)
- **Classes/interfaces/types**: PascalCase (`UserService`, `UserConfig`)
- **Files**: kebab-case for files with multiple exports (`user-service.ts`), camelCase for single class/function files (`User.ts`)
- **Test files**: `{source-file}.test.ts` (e.g., `user-service.test.ts`)
- **Boolean variables**: prefix with `is`, `has`, `can`, `should` (`isActive`, `hasPermission`)

### Error Handling
- Use try-catch blocks for async operations and expected errors
- Create custom error classes extending `Error` for domain-specific errors
- Always provide meaningful error messages
- Log errors with context before re-throwing when appropriate
- Use `Result` type or similar pattern for functions that commonly fail

```typescript
class ValidationError extends Error {
  constructor(field: string, message: string) {
    super(`Validation failed for ${field}: ${message}`);
    this.name = 'ValidationError';
  }
}
```

### Comments
- Write self-documenting code; avoid obvious comments
- Use JSDoc for public APIs and complex functions
-TODO comments should include context and ticket reference
- Keep comments up-to-date with code changes

```typescript
/**
 * Calculates the total price including tax.
 * @param items - Array of items to calculate
 * @param taxRate - Tax rate as decimal (e.g., 0.2 for 20%)
 * @returns Total price with tax
 */
function calculateTotal(items: Item[], taxRate: number): number { ... }
```

### File Structure
- One main export per file (exception: utility files with related small exports)
- Co-locate tests with source files in `__tests__` folder or as `.test.ts` files
- Keep files under 300 lines; refactor if longer
- Export types/interfaces that are used externally

### Git Commits
- Write concise, imperative commit messages ("add" not "added")
- Include scope: `feat(auth): add login endpoint`
- Keep commits focused - one logical change per commit

### Testing Guidelines
- Write unit tests for all business logic functions
- Use descriptive test names: `should return user when valid id provided`
- Follow AAA pattern: Arrange, Act, Assert
- Mock external dependencies; avoid real network/database calls
- Test edge cases and error scenarios, not just happy paths
- Keep tests simple and focused on a single behavior

```typescript
describe('getUser', () => {
  it('should return user when valid id provided', async () => {
    const mockUser = { id: '1', name: 'Test' };
    jest.spyOn(userService, 'fetch').mockResolvedValue(mockUser);

    const result = await getUser('1');

    expect(result).toEqual(mockUser);
  });

  it('should throw NotFoundError when user does not exist', async () => {
    jest.spyOn(userService, 'fetch').mockResolvedValue(null);

    await expect(getUser('999')).rejects.toThrow('User not found');
  });
});
```

### Security Guidelines
- Never commit secrets, API keys, or credentials to the repository
- Use environment variables for configuration: `process.env.API_KEY`
- Validate and sanitize all user inputs
- Avoid using `eval()`, `Function()` constructor, or dynamic code execution
- Use parameterized queries for database operations to prevent SQL injection
- Set security headers when building web applications
- Keep dependencies updated and audit regularly: `npm audit`
