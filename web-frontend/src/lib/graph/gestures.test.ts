import { describe, expect, it } from 'vitest';
import { classifyGraphGesture } from './gestures';

describe('graph gesture helpers', () => {
  it('classifies ordinary primary clicks as focus actions', () => {
    expect(classifyGraphGesture({ nodeType: 'note', durationMs: 120 })).toBe('focus');
  });

  it('classifies cmd ctrl clicks and long presses on notes as preview actions', () => {
    expect(classifyGraphGesture({ nodeType: 'note', durationMs: 80, metaKey: true })).toBe('preview');
    expect(classifyGraphGesture({ nodeType: 'note', durationMs: 80, ctrlKey: true })).toBe('preview');
    expect(classifyGraphGesture({ nodeType: 'note', durationMs: 650 })).toBe('preview');
  });

  it('keeps tag and unresolved nodes focus-only even for preview gestures', () => {
    expect(classifyGraphGesture({ nodeType: 'tag', durationMs: 650, metaKey: true })).toBe('focus');
    expect(
      classifyGraphGesture({ nodeType: 'note_or_unresolved', durationMs: 650, ctrlKey: true })
    ).toBe('focus');
  });
});
