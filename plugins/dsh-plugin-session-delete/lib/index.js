/**
 * Delete-conversation plugin, node half.
 *
 * Registers one authenticated Fetch route inside Connection's `/api` fence —
 * `POST /api/session.delete` — which permanently removes one stored Session
 * from this Host's session root, and tells the browser the row is gone.
 *
 * DSH deliberately ships no session-deletion surface: `SessionPersistence`
 * exposes `create`/`open`/`flush`/`stat`/`list` and nothing else, `/clear` and
 * archive only hide rows, and the projection cache documents pruning as
 * out-of-band maintenance. This plugin is that out-of-band step, so it owns the
 * removal itself against the layout the shipped JSONL backend writes:
 *
 *     <root>/<projectKey(header.cwd)>/<encodeSegment(sessionId)>/session[.vN].jsonl[.zstd]
 *
 * Both path builders are re-implemented below because the backend does not
 * export them; a directory scan under the session root backs them up if either
 * drifts, so a layout change degrades to "cannot find the session" instead of
 * "deleted the wrong directory". A target that is live in this process is
 * refused, because its open write handle would resurrect or corrupt the log.
 *
 * @module @deepseek-ai/dsh-client-ui-session-delete
 */
import { mkdir, readFile, readdir, realpath, rename, rm, stat, writeFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { basename, dirname, join, resolve, sep } from 'node:path'

/** The exact Fetch route this plugin owns; inside Connection's authenticated `/api` prefix. */
export const SESSION_DELETE_PATH = '/api/session.delete'

/**
 * The second route: durable per-Session facts the browser cannot see for itself.
 *
 * A stored Session's blankness lives in the Host's projection of its log. The
 * browser's Session-list row does NOT carry it for a Session that is not resident
 * (its `blank` flag describes a live Session's first turn), and its projection
 * block is loaded only for the Session being viewed — so a cleanup decided in the
 * page would see nothing to clean. This route answers from the same projection
 * cache the Session list itself uses.
 */
export const SESSION_UNUSED_PATH = '/api/session.unused'

/** List the trash, newest first. Expired entries are purged before answering. */
export const SESSION_TRASH_PATH = '/api/session.trash'

/** Put one trashed Session back where it came from. */
export const SESSION_RESTORE_PATH = '/api/session.restore'

/** Destroy one trashed Session, or every one of them, for good. */
export const SESSION_PURGE_PATH = '/api/session.purge'

/**
 * Attach stored Sessions to the workspace that owns their folder.
 *
 * The runtime attaches a Session when it is *created* (`session.create`: "create or
 * idempotently adopt one ordinary Session") and offers no entry point for one that
 * already exists — so once a folder is added as a workspace, or renamed and added
 * again, its older Sessions keep rendering under "ungrouped" with nothing in the UI
 * able to fix them. This is that one repair, and it is why the plugin runs it once at
 * startup: it never creates, moves or deletes anything, and the attach itself is
 * idempotent.
 */
export const SESSION_ADOPT_PATH = '/api/session.adopt'

/** How long a trashed Session stays restorable unless the profile says otherwise. */
const DEFAULT_RETENTION_DAYS = 7

/** The directory this plugin owns, beside the sessions root (same volume: a rename is atomic). */
const TRASH_OWNER_DIRECTORY = 'plugin-session-delete'

/** Longest accepted session id, bounded before any filesystem or lookup work. */
const MAX_SESSION_ID_LENGTH = 200

/** Rows this route will report; a profile with more stored Sessions than this is out of scope. */
const MAX_UNUSED_ROWS = 5000

/** Session ids are filesystem segments: letters, digits, `.`, `_`, `-` only. */
const SESSION_ID_PATTERN = /^[A-Za-z0-9._-]+$/

/**
 * Required Host services.
 *
 * `connection` owns the route registry and its Host/Origin + browser-token
 * fence; `sessionPersistence` resolves a stored Session's header (its `cwd`
 * picks the project directory) and the session root; `sessions` is the live
 * in-memory registry this plugin refuses to delete from under; `sessionQuery`
 * is the Host's own enumeration of stored Sessions, which is where the durable
 * per-Session facts come from.
 */
export const inject = ['connection', 'sessionPersistence', 'sessions', 'sessionQuery', 'workspaceRegistry']

/** The slice of Connection this plugin uses. */
                              
                   
                         
                                       
                                    
                                                           
                
 

/** The slice of Session persistence this plugin uses. */
                                  
                                                           
                         
                                                                                                          
 

/** The slice of the live Session registry this plugin uses. */
                            
                                 
 

/** One stored Session as the Host's query service reports it. */
                             
                    
                       
                                     
                                           
   
 

/** The slice of Session query this plugin uses. */
                            
                                                                           
 

/** One workspace as the registry reports it. */
                         
                       
                                        
                                                 
 

/** The slice of the workspace registry this plugin uses. */
                                 
                                  
 

/**
 * The slice of the projection cache this plugin uses.
 *
 * Read through `ctx.get` rather than `inject`: the cache is an optional service,
 * exactly as the Session controller itself treats it, and a profile without one
 * should serve "unproven" rows rather than refuse to compose.
 */
                                      
                                                                                                                             
 

/** Durable facts about one stored Session, as this plugin reports them. */
                                   
                            
                      
                                                                             
                                     
                                                                          
                                     
                                                                       
                                   
                                                                                        
                            
                                                                                     
                         
                                                                                  
                          
                                      
 

/** Host context this plugin applies to. */
                       
                                                             
                                                     
                                     
                                         
                                                   
                            
                                                          
                                                  
 

/** One failure envelope's shape. */
                         
                       
                          
 

/** One trashed Session, as this plugin reports it. */
                             
                            
                                                                           
                      
                                     
                                     
                                
                            
                                                                
                            
                              
                                   
 

/** The record this plugin keeps beside each trashed Session. */
                       
                            
                      
                                   
                                     
                                     
                            
                                   
 

/** How this plugin is configured in a profile's patch row. */
                                      
                                                 
                                             
 

/** One successful deletion's report. */
                        
                            
                            
                                   
                                
                                 
 

/**
 * Register this plugin's authenticated routes for its lifetime.
 * @param ctx - Host context carrying Connection, persistence, query, and live Sessions.
 * @param config - optional plugin config: how long the trash keeps things.
 */
export function apply(ctx             , config                      )       {
  ctx.effect(() => ctx.connection.fetch.register({
    path: SESSION_DELETE_PATH,
    methods: ['POST'],
    requestBody: 'buffered',
    fetch: (request) => handleSessionDelete(ctx, config, request)
  }), `session-delete: POST ${SESSION_DELETE_PATH}`)
  ctx.effect(() => ctx.connection.fetch.register({
    path: SESSION_UNUSED_PATH,
    methods: ['POST'],
    requestBody: 'buffered',
    fetch: (request) => handleSessionUnused(ctx, request)
  }), `session-delete: POST ${SESSION_UNUSED_PATH}`)
  ctx.effect(() => ctx.connection.fetch.register({
    path: SESSION_TRASH_PATH,
    methods: ['POST'],
    requestBody: 'buffered',
    fetch: (request) => handleTrashList(ctx, config, request)
  }), `session-delete: POST ${SESSION_TRASH_PATH}`)
  ctx.effect(() => ctx.connection.fetch.register({
    path: SESSION_RESTORE_PATH,
    methods: ['POST'],
    requestBody: 'buffered',
    fetch: (request) => handleSessionRestore(ctx, request)
  }), `session-delete: POST ${SESSION_RESTORE_PATH}`)
  ctx.effect(() => ctx.connection.fetch.register({
    path: SESSION_PURGE_PATH,
    methods: ['POST'],
    requestBody: 'buffered',
    fetch: (request) => handleSessionPurge(ctx, config, request)
  }), `session-delete: POST ${SESSION_PURGE_PATH}`)
  ctx.effect(() => ctx.connection.fetch.register({
    path: SESSION_ADOPT_PATH,
    methods: ['POST'],
    requestBody: 'buffered',
    fetch: (request) => handleSessionAdopt(ctx, request)
  }), `session-delete: POST ${SESSION_ADOPT_PATH}`)

  // The repair, once per start: stored Sessions whose folder is a registered
  // workspace but which were never attached to it render under "ungrouped" with no
  // UI able to fix that. Best-effort — a failure here must not stop the mount.
  ctx.effect(() => {
    void adoptStoredSessions(ctx).catch(() => {})
    return () => {}
  }, 'session-delete: attach stored Sessions to their workspaces')

  // Expiry is lazy (a list purges what has aged out), but a profile that has not
  // opened the trash for a month should not accumulate one. Best-effort: a failure
  // here must never stop the plugin from mounting.
  ctx.effect(() => {
    void expireTrash(ctx, retentionMs(config)).catch(() => {})
    return () => {}
  }, 'session-delete: expire the trash at startup')
}

/**
 * Serve one request for the durable per-Session facts.
 *
 * The body is ignored: this route reports every stored Session and lets the caller
 * apply its own policy, so it stays useful to more than the cleanup dialog.
 *
 * @param ctx - Host context.
 * @param request - the authenticated Fetch request.
 * @returns a JSON envelope whose value is `{ sessions: UnusedSessionRow[] }`.
 */
async function handleSessionUnused(ctx             , request         )                    {
  // A body is optional here; an unparsable one is still refused so a caller
  // cannot believe arguments were honoured when they were not.
  const text = await request.text()
  if (text.trim() !== '') {
    try {
      const parsed          = JSON.parse(text)
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        return failure('invalid-request', 'the request body must be a JSON object or empty', 400)
      }
    } catch {
      return failure('invalid-request', 'the request body must be a JSON object or empty', 400)
    }
  }

  let records                              
  try {
    records = await ctx.sessionQuery.listSessions()
  } catch (error) {
    return failure('storage-unreadable', `cannot list stored sessions: ${messageOf(error)}`, 500)
  }

  const cache = ctx.get('sessionProjectionCache')                                          
  const root = sessionRoot(ctx)
  const sessions                     = []
  for (const record of records.slice(0, MAX_UNUSED_ROWS)) {
    const header = record.header
    if (header.cwd === undefined || header.cwd.length === 0) continue
    // Both rows come from the same cache block the Session list itself reads: the
    // title is what the operator recognises the conversation by, and the size is
    // what the cleanup is actually reclaiming.
    let values                                               
    try {
      values = cache?.cachedSnapshot(header, ['sessionListMetadata', 'title'])?.values
    } catch {
      // A cache that cannot answer is "unproven", never an error: the caller's
      // policy must not be talked into a deletion by a failure.
      values = undefined
    }
    const metadata = values?.sessionListMetadata                                                                             
    const title = typeof values?.title === 'string' && values.title.trim() !== '' ? values.title : undefined
    const bytes = await sessionBytes(root, header.cwd, header.id)
    const lastPromptAt = typeof metadata?.lastPromptAt === 'number' ? metadata.lastPromptAt : null
    const createdAt = typeof header.createdAt === 'number' ? header.createdAt : null
    sessions.push({
      sessionId: header.id,
      cwd: header.cwd,
      ...title === undefined ? {} : { title },
      ...bytes === undefined ? {} : { bytes },
      createdAt,
      updatedAt: Math.max(createdAt ?? 0, lastPromptAt ?? 0),
      blank: metadata?.blank === true,
      proven: metadata !== undefined,
      lastPromptAt
    })
  }

  return Response.json({ ok: true, value: { sessions } }, { headers: { 'cache-control': 'no-store' } })
}

/**
 * Measure one stored Session's directory, so the cleanup can say what it reclaims.
 *
 * Best-effort by design: a Session that cannot be measured is still reported, just
 * without a size. Nothing here decides anything — the policy never reads this.
 *
 * @param root - the configured session root.
 * @param cwd - the Session's workspace path, which picks its project directory.
 * @param sessionId - the Session id.
 * @returns the total bytes of its artifacts, or `undefined` when unreadable.
 */
async function sessionBytes(root        , cwd        , sessionId        )                              {
  try {
    const directory = resolve(root, projectKey(cwd), encodeSegment(sessionId))
    if (containmentRefusal(root, directory, encodeSegment(sessionId)) !== undefined) return undefined
    const entries = await readdir(directory, { withFileTypes: true })
    let total = 0
    for (const entry of entries) {
      if (!entry.isFile()) continue
      total += (await stat(join(directory, entry.name))).size
    }
    return total
  } catch {
    return undefined
  }
}

/**
 * Serve one delete request.
 * @param ctx - Host context.
 * @param request - the authenticated Fetch request.
 * @returns a JSON envelope: `{ ok: true, value }` or `{ ok: false, error }`.
 */
async function handleSessionDelete(ctx             , config                                 , request         )                    {
  let body         
  try {
    body = await request.json()
  } catch {
    return failure('invalid-request', 'the request body must be a JSON object', 400)
  }
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    return failure('invalid-request', 'the request body must be a JSON object', 400)
  }
  const sessionId = (body                           ).sessionId
  if (typeof sessionId !== 'string' || sessionId.length === 0 || sessionId.length > MAX_SESSION_ID_LENGTH
    || !SESSION_ID_PATTERN.test(sessionId) || sessionId === '.' || sessionId === '..') {
    return failure('invalid-session-id', 'sessionId must be a session-id-shaped string', 400)
  }

  const root = sessionRoot(ctx)
  // An open conversation does NOT block this any more. `ctx.sessions.get` answers "is the
  // Session resident in this process", which stays true after switching to another
  // conversation — it is released only when the process ends — so refusing on that turned
  // "switch away and delete it" into "restart DSH and delete it". The move is attempted
  // instead and the filesystem decides: a log a turn is actually writing still fails to
  // rename, and that failure is worded for what it is.
  const resident = ctx.sessions.get(sessionId) !== undefined
  let directory                    
  try {
    directory = await locateSessionDirectory(ctx, root, sessionId)
  } catch (error) {
    return failure('storage-unreadable', `cannot read the session root "${root}": ${messageOf(error)}`, 500)
  }
  if (directory === undefined) {
    return failure('session-not-found', `no stored session log for "${sessionId}" under "${root}"`, 404)
  }

  // Containment before anything moves: the target must be exactly
  // <root>/<project>/<encoded session id>. A layout drift, a crafted id, or a
  // symlinked project directory can then only ever produce a refusal.
  const refusal = containmentRefusal(root, directory, encodeSegment(sessionId))
  if (refusal !== undefined) return failure('unsafe-target', refusal, 500)
  const realRefusal = await realContainmentRefusal(root, directory)
  if (realRefusal !== undefined) return failure('unsafe-target', realRefusal, 500)

  // Removal is a MOVE, not an unlink: the Session is renamed into this plugin's
  // trash, which lives beside the sessions root so the rename stays on one volume
  // and therefore atomic. Nothing is destroyed here — `session.purge` is what
  // destroys, and the retention window is what decides when.
  const trashed = await moveToTrash(ctx, root, sessionId, directory, config)
  if (!trashed.ok) {
    // The reason is kept, never swallowed: a log still held open by a running turn and a
    // full disk are different problems, and only one of them is worth retrying.
    if (isLockedError(trashed.error)) {
      return failure(
        'session-open',
        `the log of "${sessionId}" could not be moved: the file is still held open by this process`
        + `${resident ? ' (the Session is still resident, which switching conversations does not release)' : ''}. `
        + 'A running turn holds it until it finishes; a resident Session holds it until DSH exits.',
        409
      )
    }
    return failure('delete-failed', `cannot move "${directory}" into the trash: ${messageOf(trashed.error)}`, 500)
  }

  const cacheRemoved = await purgeProjectionRecord(ctx, sessionId)

  // The shipped Session Controller emits this when a Session leaves the live
  // registry; api-remotes forwards it to every browser, where the session-list
  // store drops the row. A disk deletion emits nothing on its own, so the
  // plugin says it here.
  ctx.emit('api-session/removed', sessionId)

  return Response.json({
    ok: true,
    value: {
      sessionId,
      directory,
      files: trashed.files,
      cacheRemoved,
      // Where it went and when it stops being restorable.
      trashEntry: trashed.entry
    }
  }, { headers: { 'cache-control': 'no-store' } })
}

/**
 * The retention window in milliseconds.
 * @param config - plugin config, when the profile set any.
 * @returns the window, defaulting to a week.
 */
function retentionMs(config                                 )         {
  const days = config?.retentionDays
  const usable = typeof days === 'number' && Number.isFinite(days) && days > 0 ? days : DEFAULT_RETENTION_DAYS
  return Math.round(usable * 24 * 60 * 60 * 1000)
}

/**
 * This plugin's own directory for a profile: beside the sessions root, so a move
 * into or out of it is a rename on one volume rather than a copy across volumes.
 * @param root - the configured session root.
 * @returns the trash directory.
 */
function trashRoot(root        )         {
  return join(dirname(root), TRASH_OWNER_DIRECTORY, 'trash')
}

/** Where one trashed Session's files live, and where its record lives. */
function trashPaths(root        , sessionId        )                                                          {
  const base = join(trashRoot(root), 'entries')
  return { directory: join(base, encodeSegment(sessionId)), record: join(base, `${encodeSegment(sessionId)}.json`) }
}

/** Read one trashed Session's record, or `undefined` when it is unreadable. */
async function readTrashRecord(root        , sessionId        )                                   {
  try {
    const raw = await readFile(trashPaths(root, sessionId).record, 'utf8')
    const parsed          = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null) return undefined
    const record = parsed                        
    if (typeof record.sessionId !== 'string' || typeof record.deletedAt !== 'number') return undefined
    return {
      sessionId: record.sessionId,
      cwd: typeof record.cwd === 'string' ? record.cwd : '',
      projectDirectory: typeof record.projectDirectory === 'string' ? record.projectDirectory : '',
      ...typeof record.title === 'string' ? { title: record.title } : {},
      ...typeof record.bytes === 'number' ? { bytes: record.bytes } : {},
      deletedAt: record.deletedAt,
      files: Array.isArray(record.files) ? record.files.filter((name)                 => typeof name === 'string') : []
    }
  } catch {
    return undefined
  }
}

/** One trashed Session as the routes report it. */
function toEntry(record             , retention        )             {
  return {
    sessionId: record.sessionId,
    cwd: record.cwd,
    ...record.title === undefined ? {} : { title: record.title },
    ...record.bytes === undefined ? {} : { bytes: record.bytes },
    deletedAt: record.deletedAt,
    expiresAt: record.deletedAt + retention,
    files: record.files
  }
}

/** Every trash record this plugin can read, newest first. */
async function listTrashRecords(root        )                                  {
  const base = join(trashRoot(root), 'entries')
  let names                   
  try {
    names = (await readdir(base)).filter((name) => name.endsWith('.json'))
  } catch {
    return []
  }
  const records                = []
  for (const name of names) {
    const record = await readTrashRecord(root, name.slice(0, -'.json'.length))
    if (record !== undefined) records.push(record)
  }
  return records.sort((left, right) => right.deletedAt - left.deletedAt)
}

/**
 * Move one Session into the trash, recording where it came from.
 *
 * A move, not a copy: the caller has already checked that `directory` is exactly
 * `<root>/<project>/<encoded id>`, so the destination is this plugin's own tree on
 * the same volume.
 *
 * @param ctx - Host context, for the projection title.
 * @param root - the configured session root.
 * @param sessionId - the validated Session id.
 * @param directory - the located, containment-checked Session directory.
 * @param config - plugin config.
 * @returns the entry it became, or `undefined` when the move failed.
 */
async function moveToTrash(
  ctx             ,
  root        ,
  sessionId        ,
  directory        ,
  config                                 
)                                                                                                                                                  {
  const paths = trashPaths(root, sessionId)
  try {
    const files = (await readdir(directory, { withFileTypes: true })).map((entry) => entry.name)
    let bytes = 0
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      if (!entry.isFile()) continue
      bytes += (await stat(join(directory, entry.name))).size
    }
    const title = await projectedTitle(ctx, sessionId, directory)
    await mkdir(paths.directory, { recursive: true })
    await rm(paths.directory, { recursive: true, force: true })
    await rename(directory, paths.directory)
    const record              = {
      sessionId,
      cwd: await workspaceOf(ctx, sessionId) ?? '',
      projectDirectory: dirname(directory),
      ...title === undefined ? {} : { title },
      bytes,
      deletedAt: Date.now(),
      files
    }
    await writeFile(paths.record, `${JSON.stringify(record, undefined, 2)}\n`, 'utf8')
    return { ok: true, entry: toEntry(record, retentionMs(config)), files }
  } catch (error) {
    // The caller words this; nothing is ever reported as done that did not happen.
    return { ok: false, error }
  }
}

/**
 * Whether a failed move means the log is still held open.
 *
 * Windows reports a file another handle has open without delete sharing as EPERM or
 * EACCES, and a directory in use as EBUSY; the same three turn up elsewhere for a busy or
 * mounted path. Anything else — a missing parent, a full disk, a target that is not a
 * directory — is a different problem and must not be worded as "close it first".
 *
 * @param error - whatever the move threw.
 * @returns true when the path is held rather than broken.
 */
export function isLockedError(error         )          {
  const code = (error                                         )?.code
  return code === 'EBUSY' || code === 'EPERM' || code === 'EACCES'
}

/** The Session's workspace path, when persistence still knows it. */
async function workspaceOf(ctx             , sessionId        )                              {
  try {
    const snapshot = await ctx.sessionPersistence.stat(sessionId)
    const cwd = snapshot?.header.cwd
    return cwd === undefined || cwd.length === 0 ? undefined : cwd
  } catch {
    return undefined
  }
}

/**
 * The title the Host's projection carries for a Session, if any.
 * @param ctx - Host context.
 * @param sessionId - the Session id.
 * @param directory - its directory, used to identify it to the cache.
 * @returns the title, or `undefined`.
 */
async function projectedTitle(ctx             , sessionId        , directory        )                              {
  const cache = ctx.get('sessionProjectionCache')                                          
  try {
    const meta = await ctx.sessionQuery.listSessions()
    const header = meta.find((record) => record.header.id === sessionId)?.header ?? { id: sessionId }
    void directory
    const values = cache?.cachedSnapshot(header, ['title'])?.values
    return typeof values?.title === 'string' && values.title.trim() !== '' ? values.title : undefined
  } catch {
    return undefined
  }
}

/**
 * Destroy trashed Sessions whose retention window has closed.
 * @param ctx - Host context.
 * @param retention - the window in milliseconds.
 * @returns how many were destroyed.
 */
async function expireTrash(ctx             , retention        )                  {
  const root = sessionRoot(ctx)
  const now = Date.now()
  let purged = 0
  for (const record of await listTrashRecords(root)) {
    if (now - record.deletedAt < retention) continue
    if (await purgeTrashEntry(root, record.sessionId)) purged++
  }
  return purged
}

/**
 * Remove one trashed Session's files and record for good.
 *
 * The containment check is the same shape as the delete path's: the directory must
 * be exactly one level below the trash's own entries directory and named after the
 * Session, so nothing here can be talked into an rm somewhere else.
 *
 * @param root - the configured session root.
 * @param sessionId - the Session id.
 * @returns whether the entry is gone afterwards.
 */
async function purgeTrashEntry(root        , sessionId        )                   {
  const paths = trashPaths(root, sessionId)
  const base = join(trashRoot(root), 'entries')
  const encoded = encodeSegment(sessionId)
  if (basename(paths.directory) !== encoded || dirname(paths.directory) !== base) return false
  try {
    await rm(paths.directory, { recursive: true, force: true })
    await rm(paths.record, { force: true })
    return true
  } catch {
    return false
  }
}

/**
 * Serve one trash listing. Expired entries are destroyed first, so what a caller
 * sees is always what is actually still restorable.
 * @param ctx - Host context.
 * @param config - plugin config.
 * @param request - the authenticated Fetch request.
 * @returns a JSON envelope whose value is `{ entries, retentionDays }`.
 */
async function handleTrashList(ctx             , config                                 , request         )                    {
  const invalid = await rejectNonEmptyBody(request)
  if (invalid !== undefined) return invalid
  const retention = retentionMs(config)
  try {
    await expireTrash(ctx, retention)
    const entries = (await listTrashRecords(sessionRoot(ctx))).map((record) => toEntry(record, retention))
    return Response.json({
      ok: true,
      value: { entries, retentionDays: Math.round(retention / (24 * 60 * 60 * 1000)) }
    }, { headers: { 'cache-control': 'no-store' } })
  } catch (error) {
    return failure('storage-unreadable', `cannot read the trash: ${messageOf(error)}`, 500)
  }
}

/**
 * Serve one restore: put a trashed Session back where it came from.
 * @param ctx - Host context.
 * @param request - the authenticated Fetch request.
 * @returns a JSON envelope, or a refusal when the destination is taken.
 */
async function handleSessionRestore(ctx             , request         )                    {
  const body = await readJsonBody(request)
  if ('response' in body) return body.response
  const sessionId = sessionIdOf(body.value)
  if (sessionId === undefined) return failure('invalid-session-id', 'sessionId must be a session-id-shaped string', 400)

  const root = sessionRoot(ctx)
  const record = await readTrashRecord(root, sessionId)
  if (record === undefined) return failure('trash-entry-not-found', `nothing in the trash for "${sessionId}"`, 404)

  const project = record.cwd === '' ? record.projectDirectory : projectDirectory(root, record.cwd)
  const target = join(project, encodeSegment(sessionId))
  const refusal = containmentRefusal(root, target, encodeSegment(sessionId))
  if (refusal !== undefined) return failure('unsafe-target', refusal, 500)
  if (await isDirectory(target)) {
    return failure('session-exists', `"${encodeSegment(sessionId)}" is already present under "${root}"`, 409)
  }

  const paths = trashPaths(root, sessionId)
  try {
    await mkdir(project, { recursive: true })
    await rename(paths.directory, target)
    await rm(paths.record, { force: true })
  } catch (error) {
    return failure('restore-failed', `cannot restore "${sessionId}": ${messageOf(error)}`, 500)
  }

  // The row it left is gone from the browser's list. Whether it reappears at once
  // depends on the runtime re-reading the sessions root; the client refreshes its
  // list either way, and a restart always picks it up.
  ctx.emit('api-session/restored', sessionId)
  return Response.json({ ok: true, value: { sessionId, directory: target } }, { headers: { 'cache-control': 'no-store' } })
}

/**
 * Serve one purge: destroy a trashed Session, or everything in the trash.
 * @param ctx - Host context.
 * @param config - plugin config.
 * @param request - the authenticated Fetch request.
 * @returns a JSON envelope reporting what was destroyed.
 */
async function handleSessionPurge(ctx             , config                                 , request         )                    {
  const body = await readJsonBody(request)
  if ('response' in body) return body.response
  const purgeAll = (body.value                     ).all === true
  const root = sessionRoot(ctx)

  if (!purgeAll) {
    const sessionId = sessionIdOf(body.value)
    if (sessionId === undefined) return failure('invalid-session-id', 'sessionId must be a session-id-shaped string, or pass all: true', 400)
    // A record must exist before a purge can claim to have destroyed anything:
    // `rm` with `force` succeeds on a missing path, so asking it alone would report
    // success for an entry that was never there.
    if (await readTrashRecord(root, sessionId) === undefined) {
      return failure('trash-entry-not-found', `nothing in the trash for "${sessionId}"`, 404)
    }
    if (!await purgeTrashEntry(root, sessionId)) {
      return failure('delete-failed', `cannot destroy the trashed "${sessionId}"`, 500)
    }
    return Response.json({ ok: true, value: { purged: [sessionId] } }, { headers: { 'cache-control': 'no-store' } })
  }

  void config
  const purged           = []
  for (const record of await listTrashRecords(root)) {
    if (await purgeTrashEntry(root, record.sessionId)) purged.push(record.sessionId)
  }
  return Response.json({ ok: true, value: { purged } }, { headers: { 'cache-control': 'no-store' } })
}

/**
 * Attach every stored Session whose folder is a registered workspace, when it is not
 * attached yet.
 *
 * The workspace path is the `fs.realpath` canon the registry stamped, and a Session's
 * header carries the path it was created in, so both sides are resolved before they
 * are compared: a folder that has been renamed resolves to nothing and is left alone,
 * and a link into a workspace counts as that workspace. Idempotent by construction —
 * an attached Session is skipped before `attachSession` is called, and the method
 * itself is a no-op for one already in the account.
 *
 * @param ctx - Host context carrying the workspace registry and Session query.
 * @returns the ids it attached, and how many stored Sessions it left alone.
 */
async function adoptStoredSessions(ctx             )                                                                             {
  const workspaces = ctx.workspaceRegistry.list()
  if (workspaces.length === 0) return { adopted: [], skipped: 0 }
  const byPath = new Map(workspaces.map((workspace) => [workspace.path, workspace]))
  let records                              
  try {
    records = await ctx.sessionQuery.listSessions()
  } catch {
    return { adopted: [], skipped: 0 }
  }

  const adopted           = []
  let skipped = 0
  for (const record of records) {
    const cwd = record.header.cwd
    if (cwd === undefined || cwd.length === 0) continue
    let real        
    try {
      real = await realpath(cwd)
    } catch {
      // The folder is gone: there is no workspace to attach to, and nothing to fix.
      skipped++
      continue
    }
    const workspace = byPath.get(real)
    if (workspace === undefined) {
      skipped++
      continue
    }
    if (workspace.sessionIds.includes(record.header.id)) continue
    try {
      await workspace.attachSession(record.header.id)
      adopted.push(record.header.id)
    } catch {
      // attachSession validates the header against the workspace path; a refusal here
      // means the two disagree, which is exactly what must not be papered over.
      skipped++
    }
  }
  return { adopted, skipped }
}

/**
 * Serve one adopt request: the same repair, on demand.
 * @param ctx - Host context.
 * @param request - the authenticated Fetch request.
 * @returns a JSON envelope reporting what it attached.
 */
async function handleSessionAdopt(ctx             , request         )                    {
  const invalid = await rejectNonEmptyBody(request)
  if (invalid !== undefined) return invalid
  try {
    const result = await adoptStoredSessions(ctx)
    return Response.json({ ok: true, value: result }, { headers: { 'cache-control': 'no-store' } })
  } catch (error) {
    return failure('adopt-failed', `cannot attach stored sessions: ${messageOf(error)}`, 500)
  }
}

/** Read a request body that must be a JSON object; empty is not allowed here. */async function readJsonBody(request         )                                                                                         {
  let parsed         
  try {
    parsed = await request.json()
  } catch {
    return { response: failure('invalid-request', 'the request body must be a JSON object', 400) }
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return { response: failure('invalid-request', 'the request body must be a JSON object', 400) }
  }
  return { value: parsed                            }
}

/** Validate a body's `sessionId`, or `undefined` when it is not acceptable. */
function sessionIdOf(body                         )                     {
  const sessionId = body.sessionId
  if (typeof sessionId !== 'string' || sessionId.length === 0 || sessionId.length > MAX_SESSION_ID_LENGTH) return undefined
  if (!SESSION_ID_PATTERN.test(sessionId) || sessionId === '.' || sessionId === '..') return undefined
  return sessionId
}

/** Refuse a body that carries anything, for routes that take none. */
async function rejectNonEmptyBody(request         )                                {
  const text = await request.text()
  if (text.trim() === '') return undefined
  try {
    const parsed          = JSON.parse(text)
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) return undefined
  } catch {}
  return failure('invalid-request', 'the request body must be a JSON object or empty', 400)
}

/**
 * Resolve one stored Session's directory beneath the session root.
 *
 * The header's `cwd` picks the project directory when persistence still knows
 * the Session; a scan of the project directories backs that up, so a Session
 * whose generation moved (or whose header is no longer listed) is still found
 * by its own directory name.
 *
 * @param ctx - Host context carrying Session persistence.
 * @param root - the configured session root.
 * @param sessionId - the validated Session id.
 * @returns the absolute session directory, or `undefined` when none exists.
 */
async function locateSessionDirectory(ctx             , root        , sessionId        )                              {
  const encoded = encodeSegment(sessionId)
  const snapshot = await ctx.sessionPersistence.stat(sessionId)
  const cwd = snapshot?.header.cwd
  // A header with no usable cwd (`undefined`, or the empty string the backend
  // itself refuses to encode) simply falls through to the scan.
  if (cwd === undefined || cwd.length > 0) {
    const candidate = join(projectDirectory(root, cwd), encoded)
    if (await isDirectory(candidate)) return candidate
  }
  const projects = await readdir(root, { withFileTypes: true })
  for (const project of projects) {
    if (!project.isDirectory()) continue
    const candidate = join(root, project.name, encoded)
    if (await isDirectory(candidate)) return candidate
  }
  return undefined
}

/**
 * Read the session root the mounted persistence backend writes to.
 *
 * `config.root` is the documented config field and the JSONL backend keeps the
 * resolved path on the instance, which is the only place a plugin can see it.
 * `DSH_HOME/sessions` is the profile's own value and the fallback.
 *
 * @param ctx - Host context carrying Session persistence.
 * @returns the absolute session root, unverified.
 */
function sessionRoot(ctx             )         {
  const persistence = ctx.sessionPersistence
  const configured = typeof persistence.config?.root === 'string' ? persistence.config.root : persistence.root
  if (typeof configured === 'string' && configured.length > 0) return resolve(configured)
  const home = process.env.DSH_HOME ?? join(homedir(), '.dsh')
  return resolve(join(home, 'sessions'))
}

/**
 * Remove one Session's projection-cache record.
 *
 * The record is a derived checkpoint keyed by Session id, and its identity
 * guard rejects a stale document anyway, so this is tidiness rather than
 * correctness: a failure is reported, never fatal.
 *
 * @param ctx - Host context carrying Session persistence (for the sibling root).
 * @param sessionId - the deleted Session id.
 * @returns whether a record was removed.
 */
async function purgeProjectionRecord(ctx             , sessionId        )                   {
  try {
    const storageRoot = resolve(join(sessionRoot(ctx), '..', 'storages', 'session_projcache', 'sessions'))
    await rm(join(storageRoot, `${encodeSegment(sessionId)}.json`), { force: true })
    return true
  } catch {
    return false
  }
}

/**
 * The project directory one Session's header belongs to.
 * @param root - the session root.
 * @param cwd - the Session header's project directory, if it carries one.
 * @returns the project directory path under the root.
 */
function projectDirectory(root        , cwd                    )         {
  if (cwd === undefined) return join(root, '_no-cwd')
  return join(root, projectKey(cwd))
}

/**
 * Decide whether a located directory is safe to remove recursively.
 * @param root - the configured session root.
 * @param directory - the located session directory.
 * @param encoded - the encoded Session id the directory must be named after.
 * @returns a refusal message, or `undefined` when the target is contained.
 */
function containmentRefusal(root        , directory        , encoded        )                     {
  const rootPath = resolve(root)
  const target = resolve(directory)
  if (basename(target) !== encoded) return `refusing to remove "${target}": it is not named after this session`
  if (!target.startsWith(`${rootPath}${sep}`)) return `refusing to remove "${target}": it is outside the session root`
  const relative = target.slice(rootPath.length + 1)
  if (relative.split(sep).length !== 2) return `refusing to remove "${target}": it is not one project directory below the session root`
  return undefined
}

/**
 * Decide the same question again, on resolved paths.
 *
 * {@link containmentRefusal} compares strings, so a project directory that is a
 * link — a junction into another drive, or something a user created — passes it
 * while the recursive removal would actually happen wherever the link points. The
 * blast radius is already bounded (the directory must be named exactly after the
 * Session id), so this is hardening rather than a fix; resolving both sides costs
 * one syscall each and removes the doubt. A root that is itself a link is fine:
 * both sides resolve through it.
 *
 * @param root - the configured session root.
 * @param directory - the located session directory.
 * @returns a refusal message, or `undefined` when the real target is contained.
 */
async function realContainmentRefusal(root        , directory        )                              {
  let realRoot        
  let realDirectory        
  try {
    realRoot = await realpath(root)
    realDirectory = await realpath(directory)
  } catch (error) {
    return `refusing to remove "${directory}": its real path could not be resolved (${messageOf(error)})`
  }
  if (!realDirectory.startsWith(`${realRoot}${sep}`)) {
    return `refusing to remove "${directory}": it resolves outside the session root, to "${realDirectory}"`
  }
  return undefined
}

/**
 * Encode one path segment exactly as the JSONL backend does, so a session
 * directory is addressed instead of guessed.
 *
 * Exported for tools and tests: this and {@link projectKey} are the two facts
 * that let a plugin find a stored Session without the backend's own path
 * helpers, and a drift between them and the backend is the one failure this
 * plugin must not have silently.
 *
 * @param raw - the unpadded value.
 * @returns a filesystem-safe single segment.
 */
export function encodeSegment(raw        )         {
  if (raw.length === 0) throw new Error('cannot encode an empty path segment')
  if (raw === '.') return '~002E'
  if (raw === '..') return '~002E~002E'
  let out = ''
  for (let index = 0; index < raw.length; index++) {
    const code = raw.charCodeAt(index)
    const character = String.fromCharCode(code)
    if (character !== '~' && /^[A-Za-z0-9._-]$/.test(character)) out += character
    else out += `~${code.toString(16).toUpperCase().padStart(4, '0')}`
  }
  return out
}

/**
 * Build the human-navigable project directory key for one cwd, exactly as the
 * JSONL backend does: separators collapse to `-`, unsafe code units escape to
 * `~XXXX`, and the whole key is wrapped in `--` and bounded.
 *
 * Exported for tools and tests; see {@link encodeSegment}.
 *
 * @param cwd - the Session header's project directory.
 * @returns one filesystem-safe directory name.
 */
export function projectKey(cwd        )         {
  if (cwd.length === 0) throw new Error('cannot encode an empty project path')
  let readable = ''
  let separatorRun = false
  for (let index = 0; index < cwd.length; index++) {
    const code = cwd.charCodeAt(index)
    const character = String.fromCharCode(code)
    if (character === '/' || character === '\\' || character === ':') {
      if (!separatorRun) readable += '-'
      separatorRun = true
    } else if (character !== '~' && /^[A-Za-z0-9._-]$/.test(character)) {
      readable += character
      separatorRun = false
    } else {
      readable += `~${code.toString(16).toUpperCase().padStart(4, '0')}`
      separatorRun = false
    }
  }
  return `--${(readable.replace(/^-+/, '') || 'root').slice(0, 251)}--`
}

/** Whether one path is an existing directory. */
async function isDirectory(path        )                   {
  try {
    return (await stat(path)).isDirectory()
  } catch {
    return false
  }
}

/** Normalize an unknown thrown value to a message. */
function messageOf(error         )         {
  return error instanceof Error ? error.message : String(error)
}

/**
 * Compose one failure envelope.
 * @param code - stable machine code the browser switches on.
 * @param message - human diagnostic.
 * @param status - HTTP status.
 * @returns the JSON response.
 */
function failure(code        , message        , status        )           {
  const error                = { code, message }
  return Response.json({ ok: false, error }, {
    status,
    headers: { 'cache-control': 'no-store' }
  })
}
