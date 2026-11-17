/** An empty selection means 'All'; selections within one field use OR logic. */
export function matchesSelectedValues(selected: readonly string[], actual: string | null | undefined): boolean {
 return selected.length === 0 || selected.includes(actual ?? '');
}

export function toggleSelectedValue(selected: readonly string[], value: string): string[] {
 return selected.includes(value) ? selected.filter(item => item !== value) : [...selected, value];
}
