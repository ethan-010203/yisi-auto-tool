# Frontend UI Guidelines

## Required Design System

- All pages, components, and layout elements must use the shadcn/ui design system.
- Reuse project UI primitives from `front/src/components/ui/` before creating new UI elements.
- Keep spacing, radius, color, typography, shadows, and interaction states consistent with shadcn/ui.

## Forbidden Patterns

- Do not introduce third-party UI component libraries.
- Do not create non-essential native CSS or one-off visual styles.
- Do not mix unrelated visual systems into Vue pages or components.

## Implementation Notes

- This project uses Vue, Vite, Radix Vue, Tailwind-compatible utility patterns, and local shadcn-style primitives.
- When a needed primitive is missing, add it under `front/src/components/ui/` using the existing component style.
- Prefer composition of existing UI primitives over custom markup and ad-hoc classes.
