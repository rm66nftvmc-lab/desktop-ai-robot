/**
 * Delete-conversation plugin, node half.
 * @module dsh-plugin-session-delete
 */
export declare const SESSION_DELETE_PATH = "/api/session.delete";
/** Required Host services. */
export declare const inject: readonly ["connection", "sessionPersistence", "sessions"];
/** Register the authenticated delete route for this plugin's lifetime. */
export declare function apply(ctx: unknown): void;
/** Encode one path segment exactly as the JSONL persistence backend does. */
export declare function encodeSegment(raw: string): string;
/** Build the project directory key for one cwd exactly as the backend does. */
export declare function projectKey(cwd: string): string;
