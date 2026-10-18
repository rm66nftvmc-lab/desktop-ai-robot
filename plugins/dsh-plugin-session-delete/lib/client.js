window.__ModuleLoader__.load({
	id: "dsh-plugin-session-delete",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		let React = require("react");
		let primitives = require("@deepseek-ai/dsh-client-ui-primitives");
		//#region src/client/locales.ts
		/**
		 * `sessionDelete` namespace dictionaries: the copy for the row menu, the
		 * per-conversation confirmation, and the blank-Session cleanup surface.
		 *
		 * The Simplified Chinese dictionary is the key-set authority; the English one
		 * is checked complete against it by `tests/locales.test.ts`.
		 *
		 * @module @deepseek-ai/dsh-client-ui-session-delete/client/locales
		 */

		/** Locale namespace this package registers and binds. */
		const LOCALE_NAMESPACE = 'sessionDelete'

		/** Simplified Chinese dictionary. */
		const zh                         = {
		  'menu.delete': '删除对话',

		  'dialog.title': '删除这个对话？',
		  'dialog.desc': '“{title}”会从列表移除：日志移入本机回收站，可以从回收站恢复。',
		  'dialog.detail': '移动的是这台机器上的会话日志（sessions 目录下该会话的整个目录）与它的投影缓存记录。回收站到期会自动清除，也可以随时在里面彻底删除。已导出的文件、附件与工作区文件不受影响；归档记录里的这个会话编号会随之下线。',
		  'dialog.open': '这次移动失败了：这条会话的日志仍被当前进程占用。切换对话不会释放它——要么等它正在跑的回合结束，要么重启 DSH 之后再删。',
		  'dialog.notFound': '没有找到这个对话的会话日志：可能已经删除，也可能在回收站里。',
		  'dialog.unsafe': '出于安全考虑拒绝了这次删除：目标路径不在会话根目录之内。',
		  'dialog.failed': '删除失败：{reason}',
		  'confirm': '移入回收站',
		  'cancel': '取消',
		  'deleting': '移动中…',
		  'close': '关闭',
		  'untitled': '未命名对话',

		  'cleanup.button': '清理空会话',
		  'cleanup.title': '清理空会话',
		  'cleanup.desc': '有 {n} 个从未使用过的空会话，将一并删除。',
		  'cleanup.detail': '空会话是创建后从未开始过任何一轮对话的会话——它们会出现在侧边栏，但里面没有任何内容，只占磁盘。清理只删除这些空会话；正在使用（打开中或运行中），以及 {minutes} 分钟内还有活动的会话都会跳过。',
		  'cleanup.none': '没有可清理的空会话。',
		  'cleanup.loading': '正在向宿主确认哪些会话从未使用过…',
		  'cleanup.unproven': '另有 {n} 个会话宿主还没有投影记录（尚未投影），无法确认是否为空，本次跳过。',
		  'cleanup.more': '…另有 {n} 个',
		  'cleanup.confirm': '删除 {n} 个',
		  'cleanup.running': '正在清理 {done}/{total}…',
		  'cleanup.done': '已删除 {done} 个空会话。',
		  'cleanup.partial': '已删除 {done} 个，{failed} 个失败（{reason}）。',
		  'cleanup.skipped': '有 {n} 个会话正在使用，已跳过。',
		  'cleanup.failed': '清理失败：{reason}',

		  'trash.button': '回收站',
		  'trash.title': '回收站',
		  'trash.loading': '正在向宿主查询回收站…',
		  'trash.empty': '回收站是空的。',
		  'trash.desc': '{n} 个对话在回收站里，日志还在磁盘上：{days} 天内可以恢复，到期自动清除。',
		  'trash.restore': '恢复',
		  'trash.purge': '彻底删除',
		  'trash.purgeAll': '清空回收站',
		  'trash.confirmPurgeAsk': '“{title}”将被永久删除，无法恢复。',
		  'trash.confirmPurgeButton': '确定删除',
		  'trash.confirmAllAsk': '清空回收站会永久删除全部 {n} 项，无法恢复。',
		  'trash.confirmAllButton': '确定清空',
		  'trash.restored': '已恢复“{title}”，回到原来的工作区。',
		  'trash.purged': '已彻底删除。',
		  'trash.purgeAllDone': '已彻底删除 {n} 项。',
		  'trash.failed': '回收站操作失败：{reason}',
		  'trash.missing': '回收站里已经没有这一项了。',
		  'trash.taken': '它原来所在的位置已被占用，无法恢复——可以先把占用它的那个对话移走。',
		  'trash.expires': '还有 {days} 天',
		  'trash.working': '处理中…',

		  'age.justNow': '刚刚',
		  'age.minutes': '{n} 分钟前',
		  'age.hours': '{n} 小时前',
		  'age.days': '{n} 天前'
		}

		/** English dictionary, complete against {@link zh}. */
		const en                         = {
		  'menu.delete': 'Delete conversation',

		  'dialog.title': 'Delete this conversation?',
		  'dialog.desc': '“{title}” leaves the list: its log moves into the trash on this machine, and can be restored from there.',
		  'dialog.detail': 'What moves is the session log on this machine (the whole session directory under the sessions root) and its projection-cache record. The trash is purged automatically once the window closes, and anything in it can be deleted for good at any time. Exported files, attachments and workspace files are untouched; the id also drops out of the archive set.',
		  'dialog.open': 'The move failed: this Session\'s log is still held open by the running process. Switching conversations does not release it — wait for its turn to finish, or restart DSH and delete it then.',
		  'dialog.notFound': 'No session log was found for this conversation: it may be deleted, or it may be in the trash.',
		  'dialog.unsafe': 'The deletion was refused for safety: the target path is not inside the session root.',
		  'dialog.failed': 'Deletion failed: {reason}',
		  'confirm': 'Move to trash',
		  'cancel': 'Cancel',
		  'deleting': 'Moving…',
		  'close': 'Close',
		  'untitled': 'Untitled conversation',

		  'cleanup.button': 'Clean up empty conversations',
		  'cleanup.title': 'Clean up empty conversations',
		  'cleanup.desc': '{n} unused empty conversations will be deleted.',
		  'cleanup.detail': 'An empty conversation is one that never started a single turn: it is listed in the sidebar, but it holds nothing and only takes up disk. Only these are removed; anything in use (open or running) and anything active within the last {minutes} minutes is skipped.',
		  'cleanup.none': 'There are no empty conversations to clean up.',
		  'cleanup.loading': 'Asking the Host which conversations were never used…',
		  'cleanup.unproven': '{n} more have no projection on the Host yet, so they could not be confirmed as empty and were skipped.',
		  'cleanup.more': '…and {n} more',
		  'cleanup.confirm': 'Delete {n}',
		  'cleanup.running': 'Cleaning up {done}/{total}…',
		  'cleanup.done': 'Deleted {done} empty conversations.',
		  'cleanup.partial': 'Deleted {done}; {failed} failed ({reason}).',
		  'cleanup.skipped': '{n} conversations are in use and were skipped.',
		  'cleanup.failed': 'Cleanup failed: {reason}',

		  'trash.button': 'Trash',
		  'trash.title': 'Trash',
		  'trash.loading': 'Asking the Host for the trash…',
		  'trash.empty': 'The trash is empty.',
		  'trash.desc': '{n} conversations are in the trash, their logs still on disk: restorable for {days} days, then purged automatically.',
		  'trash.restore': 'Restore',
		  'trash.purge': 'Delete for good',
		  'trash.purgeAll': 'Empty the trash',
		  'trash.confirmPurgeAsk': '“{title}” will be deleted for good. This cannot be undone.',
		  'trash.confirmPurgeButton': 'Delete for good',
		  'trash.confirmAllAsk': 'Emptying the trash permanently deletes all {n} entries. This cannot be undone.',
		  'trash.confirmAllButton': 'Empty it',
		  'trash.restored': 'Restored “{title}” to its workspace.',
		  'trash.purged': 'Deleted for good.',
		  'trash.purgeAllDone': 'Deleted {n} entries for good.',
		  'trash.failed': 'Trash action failed: {reason}',
		  'trash.missing': 'That entry is no longer in the trash.',
		  'trash.taken': 'Its old place is taken, so it cannot be restored — move whatever holds that name first.',
		  'trash.expires': '{days} days left',
		  'trash.working': 'Working…',

		  'age.justNow': 'just now',
		  'age.minutes': '{n} min ago',
		  'age.hours': '{n} h ago',
		  'age.days': '{n} d ago'
		}
		//#endregion
		//#region src/client/host.ts
		/**
		 * The browser half's Host calls: `POST /api/session.delete` for one conversation
		 * (a move into the trash), `POST /api/session.unused` for the durable per-Session
		 * facts, and the trash routes that list, restore and destroy what is in there —
		 * plus the wording for the failures the operator can act on.
		 *
		 * @module @deepseek-ai/dsh-client-ui-session-delete/client/host
		 */

		/** The Host route this package's node half registers inside Connection's `/api` fence. */
		const DELETE_PATH = '/api/session.delete'

		/** The Host route reporting durable per-Session facts (blankness among them). */
		const UNUSED_PATH = '/api/session.unused'

		/** The Host route listing the trash. */
		const TRASH_PATH = '/api/session.trash'

		/** The Host route restoring one trashed Session. */
		const RESTORE_PATH = '/api/session.restore'

		/** The Host route destroying trashed Sessions. */
		const PURGE_PATH = '/api/session.purge'

		/** One trashed Session, as the Host reports it. */
		                             
		                            
		                      
		                                     
		                                     
		                            
		                            
		                                   
		 

		/** What the trash listing answers. */
		                               
		                                         
		                                                                            
		                                
		 

		/** The Host's success report for one removal. */
		                               
		                            
		                            
		                                   
		                                
		                                 
		 

		/** Durable facts about one stored Session, as the Host reports them. */
		                                   
		                            
		                      
		                                                                         
		                                     
		                                                                       
		                                     
		                                   
		                            
		                                                                                            
		                         
		                                                                                 
		                          
		                                      
		 

		/** A refusal carrying the Host's stable machine code. */
		                                                     
		                       
		 

		/** Host failure codes this package words for itself; anything else keeps the Host diagnostic. */
		const WORDED_FAILURES                                   = {
		  'session-open': 'dialog.open',
		  'session-not-found': 'dialog.notFound',
		  'unsafe-target': 'dialog.unsafe'
		}

		/**
		 * Ask the Host to remove one conversation.
		 * @param sessionId - the Session to delete.
		 * @returns the Host's report.
		 * @throws {SessionDeleteFailure} carrying the Host's code and message.
		 */
		async function deleteSession(sessionId        )                        {
		  const response = await fetch(DELETE_PATH, {
		    method: 'POST',
		    headers: { 'content-type': 'application/json' },
		    body: JSON.stringify({ sessionId })
		  })
		  let payload          = null
		  try {
		    payload = await response.json()
		  } catch {
		    payload = null
		  }
		  const envelope = payload !== null && typeof payload === 'object' ? payload                            : undefined
		  if (envelope?.ok === true) return envelope.value                

		  const error = envelope?.error !== null && typeof envelope?.error === 'object'
		    ? envelope.error                           
		    : undefined
		  const failure = new Error(
		    typeof error?.message === 'string' ? error.message : `HTTP ${String(response.status)}`
		  )                                           
		  failure.code = typeof error?.code === 'string' ? error.code : 'transport'
		  throw failure
		}

		/** The reply the trash routes give; kept beside the calls that read it. */

		/**
		 * Read the Host's durable per-Session facts.
		 *
		 * The page cannot derive these: a stored Session's list row carries a live
		 * first-turn flag that says nothing about its log, and its projection block is
		 * loaded only for the Session being viewed. The Host projects every stored log, so
		 * it is asked instead of guessed at.
		 *
		 * @returns one row per stored Session, unsorted; the caller applies its policy.
		 * @throws {SessionDeleteFailure} carrying the Host's code and message.
		 */
		async function listUnusedSessions()                                       {
		  const response = await fetch(UNUSED_PATH, {
		    method: 'POST',
		    headers: { 'content-type': 'application/json' },
		    body: JSON.stringify({})
		  })
		  let payload          = null
		  try {
		    payload = await response.json()
		  } catch {
		    payload = null
		  }
		  const envelope = payload !== null && typeof payload === 'object' ? payload                            : undefined
		  if (envelope?.ok === true) {
		    const value = envelope.value                                               
		    return Array.isArray(value?.sessions) ? value.sessions                                : []
		  }

		  const error = envelope?.error !== null && typeof envelope?.error === 'object'
		    ? envelope.error                           
		    : undefined
		  const failure = new Error(
		    typeof error?.message === 'string' ? error.message : `HTTP ${String(response.status)}`
		  )                                           
		  failure.code = typeof error?.code === 'string' ? error.code : 'transport'
		  throw failure
		}

		/**
		 * Wording for the trash failures the operator can act on.
		 */
		const WORDED_TRASH_FAILURES                                   = {
		  'trash-entry-not-found': 'trash.missing',
		  'session-exists': 'trash.taken',
		  'unsafe-target': 'dialog.unsafe'
		}

		/**
		 * One POST that unwraps the Host's envelope, or throws carrying its code.
		 * @param path - the route.
		 * @param body - the JSON body.
		 * @returns the envelope's value.
		 * @throws {SessionDeleteFailure} carrying the Host's code and message.
		 */
		async function post   (path        , body         )             {
		  const response = await fetch(path, {
		    method: 'POST',
		    headers: { 'content-type': 'application/json' },
		    body: JSON.stringify(body)
		  })
		  let payload          = null
		  try {
		    payload = await response.json()
		  } catch {
		    payload = null
		  }
		  const envelope = payload !== null && typeof payload === 'object' ? payload                            : undefined
		  if (envelope?.ok === true) return envelope.value     
		  const error = envelope?.error !== null && typeof envelope?.error === 'object'
		    ? envelope.error                           
		    : undefined
		  const failure = new Error(
		    typeof error?.message === 'string' ? error.message : `HTTP ${String(response.status)}`
		  )                                           
		  failure.code = typeof error?.code === 'string' ? error.code : 'transport'
		  throw failure
		}

		/**
		 * List the trash, newest first.
		 *
		 * The Host purges anything past its retention window before answering, so an entry
		 * in this list is one that can actually still be restored.
		 *
		 * @returns the entries and the configured window.
		 * @throws {SessionDeleteFailure} carrying the Host's code and message.
		 */
		async function listTrash()                        {
		  return post              (TRASH_PATH, {})
		}

		/**
		 * Put one trashed Session back where it came from.
		 * @param sessionId - the Session to restore.
		 * @returns where it landed.
		 * @throws {SessionDeleteFailure} carrying the Host's code and message.
		 */
		async function restoreSession(sessionId        )                                                                      {
		  return post                                                            (RESTORE_PATH, { sessionId })
		}

		/**
		 * Destroy trashed Sessions for good.
		 * @param options - one Session, or everything.
		 * @returns the ids that were destroyed.
		 * @throws {SessionDeleteFailure} carrying the Host's code and message.
		 */
		async function purgeTrash(options                                                                                 )                                                  {
		  return post                                        (PURGE_PATH, options.all === true ? { all: true } : { sessionId: options.sessionId })
		}

		/**
		 * Word a trash failure for the operator.
		 * @param reason - the thrown value.
		 * @param t - the locale seat.
		 * @returns display text.
		 */
		function describeTrashFailure(reason         , t           )         {
		  const failure = reason instanceof Error ? reason : new Error(String(reason))
		  const key = WORDED_TRASH_FAILURES[(failure                        ).code]
		  if (key !== undefined) return `${t(key)}\n${failure.message}`
		  return t('trash.failed', { reason: failure.message })
		}

		/**
		 * Word one failure for the operator: the codes this package owns have their own
		 * copy, everything else keeps the Host's diagnostic.
		 * @param reason - the thrown value.
		 * @param t - the locale seat.
		 * @returns display text.
		 */
		function describeFailure(reason         , t           )         {
		  const failure = reason instanceof Error ? reason : new Error(String(reason))
		  const key = WORDED_FAILURES[(failure                        ).code]
		  if (key !== undefined) return `${t(key)}\n${failure.message}`
		  return t('dialog.failed', { reason: failure.message })
		}

		/**
		 * Word a bulk-cleanup failure, which reports a different sentence than one
		 * conversation's removal.
		 * @param reason - the thrown value.
		 * @param t - the locale seat.
		 * @returns display text.
		 */
		function describeCleanupFailure(reason         , t           )         {
		  const message = reason instanceof Error ? reason.message : String(reason)
		  return t('cleanup.failed', { reason: message })
		}
		//#endregion
		//#region src/client/pending.ts
		/**
		 * The one pending destructive request this package owns.
		 *
		 * A menu row, a sidebar action, and the overlay dialogs are separate slot
		 * entries in separate scopes, so they cannot pass props to each other; this
		 * module-scoped store is their only channel. It is deliberately tiny and
		 * subscription-based rather than the slot `store` seat: the dialogs are
		 * root-scoped overlays with no per-occurrence identity to key a store by.
		 *
		 * @module @deepseek-ai/dsh-client-ui-session-delete/client/pending
		 */


		/** One conversation's removal request, opened from its row menu. */
		                                
		                         
		                            
		                               
		 

		/**
		 * A bulk blank-Session cleanup request, opened from the sidebar action.
		 *
		 * The durable facts come from the Host, so the request carries its own load state:
		 * the dialog cannot decide anything until they arrive, and the page has no other
		 * way to learn whether a stored Session is blank.
		 */
		                                 
		                          
		                                                           
		                           
		                                          
		                                                         
		                                                                    
		                              
		 

		/**
		 * A trash request, opened from the sidebar foot.
		 *
		 * Like the cleanup, it reads the Host first: what is restorable is the Host's
		 * answer, and the dialog shows what it is waiting for until it arrives.
		 */
		                               
		                        
		                                                    
		                           
		                                      
		                                                      
		                                                            
		                                             
		                                                                    
		                              
		 

		/** Either pending request. */
		                                                                          

		let pending                        = null
		const listeners = new Set            ()

		/** Notify every mounted subscriber. */
		function publish()       {
		  for (const listener of [...listeners]) listener()
		}

		/**
		 * Read the pending request inside a component.
		 * @returns the current request, or null.
		 */
		function usePendingRequest()                        {
		  const [value, setValue] = React.useState                       (pending)
		  React.useEffect(() => {
		    const listener = ()       => {
		      setValue(pending)
		    }
		    listeners.add(listener)
		    // Re-read once on mount: the request may have opened between render and effect.
		    listener()
		    return () => {
		      listeners.delete(listener)
		    }
		  }, [])
		  return value
		}

		/** Open the confirmation for one conversation. */
		function requestDelete(sessionId        , displayTitle        )       {
		  pending = { kind: 'delete', sessionId, displayTitle }
		  publish()
		}

		/**
		 * Open the blank-Session cleanup confirmation.
		 *
		 * The Host is asked for the durable per-Session facts first, and the dialog shows
		 * its loading state until they arrive. A failure is carried on the request so the
		 * dialog can word it, rather than being swallowed into an empty plan — which would
		 * read as "nothing to clean" when the truth is "we could not find out".
		 */
		function requestCleanup()       {
		  pending = { kind: 'cleanup', loading: true }
		  publish()
		  void listUnusedSessions().then(
		    (rows) => {
		      // A newer request (or a dismissal) owns the store now; drop this answer.
		      if (pending === null || pending.kind !== 'cleanup') return
		      pending = { kind: 'cleanup', loading: false, rows }
		      publish()
		    },
		    (error         ) => {
		      if (pending === null || pending.kind !== 'cleanup') return
		      pending = { kind: 'cleanup', loading: false, loadError: error }
		      publish()
		    }
		  )
		}

		/**
		 * Open the trash.
		 *
		 * The listing comes from the Host (it expires what has aged out before answering),
		 * so the dialog waits for it the same way the cleanup does, and a failure is carried
		 * rather than shown as an empty trash — "nothing to restore" and "we could not ask"
		 * are very different things to tell someone who just deleted a conversation.
		 */
		function requestTrash()       {
		  pending = { kind: 'trash', loading: true }
		  publish()
		  void listTrash().then(
		    (listing) => {
		      if (pending === null || pending.kind !== 'trash') return
		      pending = { kind: 'trash', loading: false, entries: listing.entries, retentionDays: listing.retentionDays }
		      publish()
		    },
		    (error         ) => {
		      if (pending === null || pending.kind !== 'trash') return
		      pending = { kind: 'trash', loading: false, loadError: error }
		      publish()
		    }
		  )
		}

		/**
		 * Re-read the trash into an open request, after a restore or a purge changed it.
		 * @param current - the request the dialog is showing.
		 */
		function refreshTrash(current              )       {
		  if (pending === null || pending.kind !== 'trash') return
		  pending = { kind: 'trash', loading: true, entries: current.entries, retentionDays: current.retentionDays }
		  publish()
		  void listTrash().then(
		    (listing) => {
		      if (pending === null || pending.kind !== 'trash') return
		      pending = { kind: 'trash', loading: false, entries: listing.entries, retentionDays: listing.retentionDays }
		      publish()
		    },
		    (error         ) => {
		      if (pending === null || pending.kind !== 'trash') return
		      pending = { kind: 'trash', loading: false, loadError: error }
		      publish()
		    }
		  )
		}

		/** Close the pending confirmation (accepted, cancelled, or dismissed). */
		function settleRequest()       {
		  pending = null
		  publish()
		}
		//#endregion
		//#region src/client/DeleteSessionMenuItem.ts
		/**
		 * The Session row's "..." menu row: order 900, after the shipped
		 * pin/rename/fork/archive rows, marked as a destructive action.
		 *
		 * @module @deepseek-ai/dsh-client-ui-session-delete/client/DeleteSessionMenuItem
		 */



		/** Owner share plus the slot's menu hook and this package's locale seat. */
		                                             
		                               
		                            
		                                                            
		                               
		                                                           
		                                             
		                                                       
		                       
		 

		/**
		 * Render the delete row.
		 * @param props - the row's owner share, menu hook, and locale seat.
		 * @returns the danger menu row that opens the confirmation.
		 */
		function DeleteSessionMenuItem(props                            )                     {
		  const [, setMenuOpen] = props.useMenuOpenState()
		  return React.createElement(primitives.MenuItemButton, {
		    danger: true,
		    separatorBefore: true,
		    icon: React.createElement(primitives.IconTrashOutlineRegular, { size: 14 }),
		    onSelect: () => {
		      setMenuOpen(false)
		      requestDelete(props.sessionId, props.displayTitle)
		    },
		    children: props.t('menu.delete')
		  })
		}
		//#endregion
		//#region src/client/DeleteSessionDialog.ts
		/**
		 * The `shell.overlay` entry for one conversation's removal: nothing while no
		 * delete is pending, otherwise one modal. The Modal portals to `document.body`,
		 * so the overlay slot only supplies the mount point.
		 *
		 * @module @deepseek-ai/dsh-client-ui-session-delete/client/DeleteSessionDialog
		 */




		/** The slot gives the entry its locale seat and the refresh hop. */
		                                           
		                                                       
		                       
		                                                                     
		                                                                
		 

		/**
		 * Render the pending confirmation, if any.
		 * @param props - the locale seat and the refresh hop.
		 * @returns the open dialog, or null.
		 */
		function DeleteSessionDialog(props                          )                            {
		  const request = usePendingRequest()
		  if (request === null || request.kind !== 'delete') return null
		  return React.createElement(DeleteSessionForm, {
		    key: request.sessionId,
		    request,
		    t: props.t,
		    refreshSessions: props.refreshSessions
		  })
		}

		/** One request's dialog: in-flight and error state die with it. */
		                                  
		                                 
		                       
		                                                                
		 

		/**
		 * Render one removal confirmation.
		 * @param props - the request, the locale seat, and the refresh hop.
		 * @returns the confirmation modal.
		 */
		function DeleteSessionForm(props                        )                     {
		  const [busy, setBusy] = React.useState(false)
		  const [failure, setFailure] = React.useState               (null)

		  const close = ()       => {
		    if (!busy) settleRequest()
		  }
		  const confirm = ()       => {
		    setBusy(true)
		    setFailure(null)
		    deleteSession(props.request.sessionId).then(() => {
		      setBusy(false)
		      settleRequest()
		      return props.refreshSessions(props.request.sessionId)
		    }).catch((reason         ) => {
		      setBusy(false)
		      setFailure(describeFailure(reason, props.t))
		    })
		  }

		  return React.createElement(primitives.Modal, {
		    open: true,
		    onClose: close,
		    closeLabel: props.t('close'),
		    title: props.t('dialog.title'),
		    description: props.t('dialog.desc', { title: props.request.displayTitle || props.t('untitled') }),
		    footer: React.createElement(React.Fragment, null, React.createElement(primitives.Button, {
		      variant: 'outline',
		      disabled: busy,
		      onClick: close,
		      children: props.t('cancel')
		    }), React.createElement(primitives.Button, {
		      variant: 'primary',
		      disabled: busy,
		      onClick: confirm,
		      children: busy ? props.t('deleting') : props.t('confirm')
		    })),
		    children: [
		      React.createElement('p', { key: 'detail', children: props.t('dialog.detail') }),
		      failure !== null && React.createElement('p', { key: 'failure', role: 'alert', children: failure })
		    ]
		  })
		}
		//#endregion
		//#region src/client/CleanupButton.ts
		/**
		 * The sidebar-foot action that opens blank-Session cleanup: an icon-only
		 * control in the rail, icon plus label when the column is wide.
		 *
		 * @module @deepseek-ai/dsh-client-ui-session-delete/client/CleanupButton
		 */



		/** Owner share of a sidebar-foot action plus this package's locale seat. */
		                                     
		                                                                      
		                        
		                                                       
		                       
		 

		/**
		 * Render the cleanup trigger.
		 * @param props - the column state and the locale seat.
		 * @returns the action button.
		 */
		function CleanupButton(props                    )                     {
		  const label = props.t('cleanup.button')
		  const icon = React.createElement(primitives.IconTrashOutlineRegular, { size: 16 })
		  const onClick = ()       => {
		    requestCleanup()
		  }
		  if (!props.wide) {
		    return React.createElement(primitives.Button, {
		      variant: 'icon',
		      size: 'sm',
		      icon,
		      title: label,
		      'aria-label': label,
		      onClick
		    })
		  }
		  return React.createElement(primitives.Button, {
		    variant: 'ghost',
		    size: 'sm',
		    icon,
		    onClick,
		    children: label
		  })
		}
		//#endregion
		//#region src/client/cleanup-plan.ts
		/**
		 * Blank-Session cleanup planning: which unused Sessions a cleanup run may
		 * remove, decided from the client list snapshot alone.
		 *
		 * Pure and React-free on purpose — it is the half of the cleanup surface that
		 * can be reasoned about and tested without a browser (see
		 * `tests/cleanup-plan.test.ts`).
		 *
		 * @module @deepseek-ai/dsh-client-ui-session-delete/client/cleanup-plan
		 */


		/**
		 * How long a blank Session must have been idle before cleanup may remove it.
		 *
		 * A blank Session is one that never started a turn, so it holds no work — but
		 * the window between "New Session" and the first message is also blank, and a
		 * second window can be sitting in that window. The grace period turns that
		 * narrow race into "leave it alone for an hour".
		 */
		const BLANK_IDLE_GRACE_MS = 60 * 60 * 1000

		/** Rows the cleanup dialog lists before collapsing the rest into a count. */
		const CLEANUP_LIST_LIMIT = 8

		/** One Session the plan selected for removal. */
		                                
		                            
		                            
		                                   
		                                                                 
		                                     
		                                                                  
		                                     
		 

		/** What one cleanup run would do, and why each blank Session was passed over. */
		                              
		                                                              
		                                            
		                                                             
		                             
		                                                        
		                                 
		                                                                             
		                                 
		                                                          
		                               
		                                                                        
		                                  
		 

		/** What the plan is decided from. */
		                               
		                                                             
		                                             
		                                                                                      
		                                             
		 

		/**
		 * Decide which blank Sessions a cleanup run may remove.
		 *
		 * Blankness is taken from the **Host's durable projection** and from nothing else.
		 * Two earlier attempts to derive it in the page failed for the same underlying
		 * reason: a stored Session's list row carries a live first-turn flag that says
		 * nothing about its log, and its projection block is loaded only for the Session
		 * being viewed. A row the Host could not prove is skipped rather than guessed at —
		 * this runs before an irreversible removal, so "unknown" must never mean "yes".
		 *
		 * @param input - the Host's facts plus the client's live list.
		 * @param now - the clock to measure the grace period against.
		 * @param graceMs - the idle grace period.
		 * @returns the plan, with each skip rule counted for the dialog's copy.
		 */
		function planBlankCleanup(
		  input              ,
		  now         = Date.now(),
		  graceMs         = BLANK_IDLE_GRACE_MS
		)              {
		  const targets                  = []
		  let considered = 0
		  let currentSkipped = 0
		  let runningSkipped = 0
		  let freshSkipped = 0
		  let unprovenSkipped = 0

		  for (const fact of input.facts) {
		    if (!fact.proven) {
		      unprovenSkipped++
		      continue
		    }
		    // Proven to have started a turn: not a candidate, and nothing to explain.
		    if (!fact.blank) continue
		    considered++
		    if (fact.sessionId === input.live?.current) {
		      currentSkipped++
		      continue
		    }
		    if (input.live?.byId[fact.sessionId]?.running === true) {
		      runningSkipped++
		      continue
		    }
		    const updatedAt = Math.max(fact.updatedAt, fact.lastPromptAt ?? 0)
		    if (now - updatedAt < graceMs) {
		      freshSkipped++
		      continue
		    }
		    targets.push({
		      sessionId: fact.sessionId,
		      updatedAt,
		      ...fact.cwd === undefined ? {} : { cwd: fact.cwd },
		      ...fact.title === undefined ? {} : { title: fact.title },
		      ...fact.bytes === undefined ? {} : { bytes: fact.bytes }
		    })
		  }

		  targets.sort((left, right) => left.updatedAt - right.updatedAt)
		  return { targets, considered, currentSkipped, runningSkipped, freshSkipped, unprovenSkipped }
		}

		/**
		 * Word one timestamp as an age, through the locale seat.
		 * @param updatedAt - durable activity timestamp.
		 * @param now - the clock to measure against.
		 * @param t - the locale seat.
		 * @returns display text such as `3 小时前`.
		 */
		function describeAge(updatedAt        , now        , t           )         {
		  const minutes = Math.floor(Math.max(0, now - updatedAt) / 60_000)
		  if (minutes < 1) return t('age.justNow')
		  if (minutes < 60) return t('age.minutes', { n: minutes })
		  const hours = Math.floor(minutes / 60)
		  if (hours < 24) return t('age.hours', { n: hours })
		  return t('age.days', { n: Math.floor(hours / 24) })
		}

		/** The grace period as whole minutes, for the dialog's copy. */
		function graceMinutes(graceMs         = BLANK_IDLE_GRACE_MS)         {
		  return Math.round(graceMs / 60_000)
		}
		//#endregion
		//#region src/client/CleanupDialog.ts
		/**
		 * The `shell.overlay` entry for blank-Session cleanup: one modal that lists what
		 * will go, runs the removals one at a time, and reports the outcome.
		 *
		 * The plan is computed from the client list snapshot (see `cleanup-plan.ts`), and
		 * each removal is the same authenticated Host call the row menu uses, so cleanup
		 * needs no Host surface of its own.
		 *
		 * @module @deepseek-ai/dsh-client-ui-session-delete/client/CleanupDialog
		 */





		/** Selector hook handed to root-scoped slot entries by the renderer. */
		                                                                          

		/** The slot gives the entry its locale seat, the list hook, and the refresh hop. */
		                                     
		                                                       
		                       
		                                       
		                                   
		                                                                   
		                                               
		 

		/** What the dialog is doing right now. */
		                    
		                                                
		                            
		                          
		                         
		                        
		                                      
		 

		const INITIAL_RUN           = {
		  phase: 'confirm',
		  attempted: 0,
		  removed: 0,
		  failed: 0,
		  inUse: 0,
		  firstFailure: null
		}

		/**
		 * Render the pending cleanup, if any.
		 * @param props - the locale seat, the list hook, and the refresh hop.
		 * @returns the open dialog, or null.
		 */
		function CleanupDialog(props                    )                            {
		  const request = usePendingRequest()
		  if (request === null || request.kind !== 'cleanup') return null
		  // One clock per opening: the grace window and every age read the same instant,
		  // so the list cannot drift while the operator reads it.
		  return React.createElement(CleanupForm, {
		    key: 'cleanup',
		    t: props.t,
		    useSessions: props.useSessions,
		    refreshSessions: props.refreshSessions,
		    request
		  })
		}

		/**
		 * Render one cleanup confirmation and its run.
		 * @param props - the locale seat, the list hook, the refresh hop, and the request.
		 * @returns the cleanup modal.
		 */
		function CleanupForm(props                                                           )                     {
		  const snapshot = props.useSessions((list) => list)
		  const [openedAt] = React.useState(() => Date.now())
		  const [run, setRun] = React.useState          (INITIAL_RUN)
		  const plan = React.useMemo(
		    () => planBlankCleanup({ facts: props.request.rows ?? [], live: snapshot }, openedAt),
		    [props.request.rows, snapshot, openedAt]
		  )

		  const running = run.phase === 'running'
		  const close = ()       => {
		    if (!running) settleRequest()
		  }

		  const confirm = ()       => {
		    const targets = plan.targets
		    setRun({ ...INITIAL_RUN, phase: 'running' })
		    void runCleanup(targets, (patch) => {
		      setRun((previous) => ({ ...previous, ...patch }))
		    }).then(async (settled) => {
		      setRun({ ...settled, phase: 'done' })
		      await props.refreshSessions()
		    })
		  }

		  // The durable facts are a Host round-trip, so the dialog has three states before
		  // its run: loading, a load failure, and the plan itself.
		  const loading = props.request.loading
		  const loadError = props.request.loadError

		  return React.createElement(primitives.Modal, {
		    open: true,
		    onClose: close,
		    closeLabel: props.t('close'),
		    title: props.t('cleanup.title'),
		    description: loadError !== undefined
		      ? describeCleanupFailure(loadError, props.t)
		      : loading
		        ? props.t('cleanup.loading')
		        : describeRun(plan, run, props.t),
		    footer: React.createElement(React.Fragment, null, React.createElement(primitives.Button, {
		      variant: 'outline',
		      disabled: running,
		      onClick: close,
		      children: run.phase === 'done' ? props.t('close') : props.t('cancel')
		    }), run.phase === 'confirm' && !loading && loadError === undefined && plan.targets.length > 0 && React.createElement(primitives.Button, {
		      variant: 'primary',
		      disabled: running,
		      onClick: confirm,
		      children: props.t('cleanup.confirm', { n: plan.targets.length })
		    })),
		    children: loadError !== undefined
		      ? null
		      : loading
		        ? null
		        : run.phase === 'confirm'
		          ? renderPlan(plan, openedAt, props.t)
		          : renderRun(run, plan.targets.length, props.t)
		  })
		}

		/**
		 * Remove the planned Sessions one at a time, reporting progress after each.
		 * Sequential on purpose: every removal is a filesystem operation on the Host,
		 * and a burst of parallel requests buys nothing but interleaved failures.
		 *
		 * @param targets - the planned Sessions, oldest activity first.
		 * @param report - progress sink.
		 * @returns the settled counts, without a phase.
		 */
		async function runCleanup(
		  targets                        ,
		  report                                    
		)                    {
		  let attempted = 0
		  let removed = 0
		  let failed = 0
		  let inUse = 0
		  let firstFailure                = null

		  for (const target of targets) {
		    try {
		      await deleteSession(target.sessionId)
		      removed++
		    } catch (reason) {
		      const code = (reason                        ).code
		      if (code === 'session-open') inUse++
		      else {
		        failed++
		        firstFailure ??= reason instanceof Error ? reason.message : String(reason)
		      }
		    }
		    attempted++
		    report({ attempted, removed, failed, inUse, firstFailure })
		  }

		  return { ...INITIAL_RUN, attempted, removed, failed, inUse, firstFailure }
		}

		/**
		 * Word the modal's description for the current phase.
		 * @param plan - the computed plan.
		 * @param run - the current run state.
		 * @param t - the locale seat.
		 * @returns the description line.
		 */
		function describeRun(plan             , run          , t           )         {
		  if (run.phase === 'confirm') {
		    if (plan.targets.length === 0) {
		      // "Nothing to clean" is worth qualifying when the reason is that blankness
		      // could not be proven yet — otherwise the operator reads it as "there is
		      // nothing there", which is what a projection-less snapshot looks like.
		      const none = t('cleanup.none')
		      return plan.unprovenSkipped > 0
		        ? `${none}\n${t('cleanup.unproven', { n: plan.unprovenSkipped })}`
		        : none
		    }
		    return t('cleanup.desc', { n: plan.targets.length })
		  }
		  if (run.phase === 'running') return t('cleanup.running', { done: run.attempted, total: plan.targets.length })
		  if (run.failed > 0) {
		    return t('cleanup.partial', {
		      done: run.removed,
		      failed: run.failed,
		      reason: run.firstFailure ?? ''
		    })
		  }
		  const done = t('cleanup.done', { done: run.removed })
		  return run.inUse > 0 ? `${done}\n${t('cleanup.skipped', { n: run.inUse })}` : done
		}

		/**
		 * Render the pre-confirmation body: the skip rules and the rows that will go.
		 * @param plan - the computed plan.
		 * @param openedAt - the instant the dialog opened.
		 * @param t - the locale seat.
		 * @returns the body nodes.
		 */
		function renderPlan(plan             , openedAt        , t           )                  {
		  const shown = plan.targets.slice(0, CLEANUP_LIST_LIMIT)
		  const hidden = plan.targets.length - shown.length
		  return [
		    React.createElement('p', { key: 'detail', children: t('cleanup.detail', { minutes: graceMinutes() }) }),
		    shown.length > 0 && React.createElement('div', {
		      key: 'rows',
		      style: { display: 'flex', flexDirection: 'column', gap: '4px', maxHeight: '220px', overflowY: 'auto' }
		    }, shown.map((target) => React.createElement('div', {
		      key: target.sessionId,
		      style: { display: 'flex', justifyContent: 'space-between', gap: '12px', fontSize: '13px' }
		    }, [
		      // The title is what the operator recognises the conversation by; the path is
		      // the fallback for one that never got a title. The size says what the run is
		      // actually reclaiming.
		      React.createElement('span', {
		        key: 'name',
		        style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
		        title: target.cwd,
		        children: target.title ?? target.cwd ?? target.sessionId
		      }),
		      React.createElement('span', {
		        key: 'meta',
		        style: { whiteSpace: 'nowrap', opacity: 0.75 },
		        children: [formatBytes(target.bytes), describeAge(target.updatedAt, openedAt, t)].filter(Boolean).join(' · ')
		      })
		    ]))),
		    hidden > 0 && React.createElement('p', { key: 'more', children: t('cleanup.more', { n: hidden }) })
		  ]
		}


		/**
		 * Render the running or finished body: the outcome already reads in the
		 * description, so only an in-flight run adds a live progress line here.
		 * @param run - the current run state.
		 * @param total - how many removals the run plans.
		 * @param t - the locale seat.
		 * @returns the body nodes, or an empty list when there is nothing to add.
		 */
		function renderRun(run          , total        , t           )                  {
		  if (run.phase !== 'running') return []
		  return [
		    React.createElement('p', {
		      key: 'progress',
		      role: 'status',
		      children: t('cleanup.running', { done: run.attempted, total })
		    })
		  ]
		}
		//#endregion
		//#region src/client/TrashButton.ts
		/**
		 * The sidebar-foot action that opens the trash: an icon-only control in the rail,
		 * icon plus label (and a count when there is something in there) when the column is
		 * wide.
		 *
		 * The count matters more than it looks: a restore window is only useful if the
		 * operator remembers there is something to restore.
		 *
		 * @module @deepseek-ai/dsh-client-ui-session-delete/client/TrashButton
		 */



		/** Owner share of a sidebar-foot action plus this package's locale seat. */
		                                   
		                                                                      
		                        
		                                                       
		                       
		 

		/**
		 * Render the trash trigger.
		 * @param props - the column state and the locale seat.
		 * @returns the action button.
		 */
		function TrashButton(props                  )                     {
		  const label = props.t('trash.button')
		  // A clock, not a bin: what this opens is a place things can come back from.
		  // (Checked against the primitives' own icon list rather than guessed: a name that
		  // does not exist would take the whole page's plugin boot down with it.)
		  const icon = React.createElement(primitives.IconClockOutlineRegular, { size: 16 })
		  const onClick = ()       => {
		    requestTrash()
		  }
		  if (!props.wide) {
		    return React.createElement(primitives.Button, {
		      variant: 'icon',
		      size: 'sm',
		      icon,
		      title: label,
		      'aria-label': label,
		      onClick
		    })
		  }
		  return React.createElement(primitives.Button, {
		    variant: 'ghost',
		    size: 'sm',
		    icon,
		    onClick,
		    children: label
		  })
		}
		//#endregion
		//#region src/client/format.ts
		/**
		 * Small display helpers shared by this package's surfaces.
		 *
		 * Their own module because the client bundle is assembled into one flat factory
		 * scope: two modules declaring the same top-level name is a build error, so anything
		 * two dialogs need lives here once.
		 *
		 * @module @deepseek-ai/dsh-client-ui-session-delete/client/format
		 */

		/**
		 * Word a byte count for the operator, or nothing when it is unknown.
		 *
		 * Decimal units, one fraction digit: this answers "roughly how much", and a fake
		 * precision would mislead. An unknown size renders as an empty string so callers can
		 * drop it out of a `·`-joined line.
		 *
		 * @param bytes - the measured size, when the Host could measure it.
		 * @returns display text such as `12.4 MB`, or an empty string.
		 */
		function formatBytes(bytes                    )         {
		  if (bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return ''
		  if (bytes < 1000) return `${String(Math.round(bytes))} B`
		  const units = ['kB', 'MB', 'GB', 'TB']
		  let value = bytes / 1000
		  let unit = 0
		  while (value >= 1000 && unit < units.length - 1) {
		    value /= 1000
		    unit++
		  }
		  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[unit] ?? 'TB'}`
		}
		//#endregion
		//#region src/client/TrashDialog.ts
		/**
		 * The trash surface: what this plugin moved out of the Session list, with the two
		 * actions that decide its fate — put it back, or destroy it now.
		 *
		 * It reads the Host on open (which also expires whatever has aged out), so what it
		 * shows is exactly what is still restorable. Rows carry the title and size the Host
		 * recorded when the Session was moved, and each action refreshes the listing rather
		 * than patching it locally: the Host is the one that knows.
		 *
		 * @module @deepseek-ai/dsh-client-ui-session-delete/client/TrashDialog
		 */





		/** Owner share of the trash overlay plus this package's locale seat. */
		                                   
		                                                       
		                       
		 

		/** What the dialog is doing right now. */
		                         
		                                             
		                                                                                  
		                              
		                          
		                                                                 
		                                
		                                                  
		                           
		                                                                
		                             
		                                                      
		                                  
		 

		const TRASH_INITIAL_RUN                = {
		  phase: 'idle',
		  note: null,
		  failed: false,
		  busyId: null,
		  busyAll: false,
		  askingAll: false,
		  askingId: null
		}

		/**
		 * The colour of the actions here that cannot be undone.
		 *
		 * `Button` has no danger variant — only `primary`, `ghost`, `outline` and `toolbar` — but
		 * the theme's destructive colour is a published token (it is what the menu row's `danger`
		 * uses), so the red comes from the same place the rest of the UI takes it rather than from
		 * a literal. It stays red text on the outline, before and during the confirmation: what
		 * changes at that step is the label and the warning above it, not a slab of colour.
		 */
		const DESTRUCTIVE_TEXT = { color: 'var(--dsw-alias-state-error-primary)' }

		/**
		 * Render the pending trash, if any.
		 * @param props - the locale seat.
		 * @returns the open dialog, or null.
		 */
		function TrashDialog(props                  )                            {
		  const request = usePendingRequest()
		  if (request === null || request.kind !== 'trash') return null
		  return React.createElement(TrashForm, { key: 'trash', t: props.t, request })
		}

		/**
		 * Render one trash listing and its actions.
		 * @param props - the locale seat and the request it belongs to.
		 * @returns the trash modal.
		 */
		function TrashForm(props                                                       )                     {
		  const [run, setRun] = React.useState               (TRASH_INITIAL_RUN)
		  const entries = props.request.entries ?? []
		  const loading = props.request.loading
		  const loadError = props.request.loadError
		  const working = run.busyId !== null || run.busyAll

		  const close = ()       => {
		    if (!working) settleRequest()
		  }

		  /** Run one action, then re-read the listing the Host now has. */
		  const act = (options                                                                                 )       => {
		    setRun((previous) => ({
		      ...previous,
		      phase: 'working',
		      note: null,
		      failed: false,
		      busyId: options.sessionId ?? null,
		      busyAll: options.all === true,
		      askingId: null,
		      askingAll: false
		    }))
		    void purgeTrash(options).then(
		      (result) => {
		        setRun((previous) => ({
		          ...previous,
		          phase: 'done',
		          note: options.all === true
		            ? props.t('trash.purgeAllDone', { n: result.purged.length })
		            : props.t('trash.purged'),
		          failed: false,
		          busyId: null,
		          busyAll: false
		        }))
		        refreshTrash(props.request)
		      },
		      (error         ) => {
		        setRun((previous) => ({
		          ...previous,
		          phase: 'done',
		          note: describeTrashFailure(error, props.t),
		          failed: true,
		          busyId: null,
		          busyAll: false
		        }))
		      }
		    )
		  }

		  /** Put one Session back, then refresh. */
		  const restore = (entry            )       => {
		    setRun((previous) => ({ ...previous, phase: 'working', note: null, failed: false, busyId: entry.sessionId }))
		    void restoreSession(entry.sessionId).then(
		      () => {
		        setRun((previous) => ({
		          ...previous,
		          phase: 'done',
		          note: props.t('trash.restored', { title: entry.title ?? entry.cwd }),
		          failed: false,
		          busyId: null
		        }))
		        refreshTrash(props.request)
		      },
		      (error         ) => {
		        setRun((previous) => ({
		          ...previous,
		          phase: 'done',
		          note: describeTrashFailure(error, props.t),
		          failed: true,
		          busyId: null
		        }))
		      }
		    )
		  }

		  const footer = React.createElement(React.Fragment, null, React.createElement(primitives.Button, {
		    variant: 'outline',
		    disabled: working,
		    onClick: close,
		    children: props.t('close')
		  }), entries.length > 0 && run.askingAll
		    ? React.createElement(primitives.Button, {
		      variant: 'outline',
		      style: DESTRUCTIVE_TEXT,
		      disabled: working,
		      onClick: () => { act({ all: true, label: props.t('trash.purgeAll') }) },
		      children: props.t('trash.confirmAllButton')
		    })
		    : entries.length > 0 && React.createElement(primitives.Button, {
		      variant: 'outline',
		      style: DESTRUCTIVE_TEXT,
		      disabled: working,
		      onClick: () => { setRun((previous) => ({ ...previous, askingAll: true, askingId: null })) },
		      children: props.t('trash.purgeAll')
		    }))

		  return React.createElement(primitives.Modal, {
		    open: true,
		    onClose: close,
		    closeLabel: props.t('close'),
		    title: props.t('trash.title'),
		    description: loadError !== undefined
		      ? describeTrashFailure(loadError, props.t)
		      : loading && entries.length === 0
		        ? props.t('trash.loading')
		        : entries.length === 0
		          ? props.t('trash.empty')
		          : props.t('trash.desc', { n: entries.length, days: props.request.retentionDays ?? 7 }),
		    footer,
		    children: [
		      // The warning is a line of red text, not a red button label: the operator reads
		      // what is about to be destroyed before reaching for the control, and the control
		      // itself stays a two-word label.
		      run.askingAll && React.createElement('p', {
		        key: 'asking-all',
		        role: 'alert',
		        style: { ...DESTRUCTIVE_TEXT, margin: 0 }
		      }, props.t('trash.confirmAllAsk', { n: entries.length })),
		      run.askingId !== null && React.createElement('p', {
		        key: 'asking-one',
		        role: 'alert',
		        style: { ...DESTRUCTIVE_TEXT, margin: 0 }
		      }, props.t('trash.confirmPurgeAsk', {
		        title: entries.find((entry) => entry.sessionId === run.askingId)?.title
		          ?? entries.find((entry) => entry.sessionId === run.askingId)?.cwd
		          ?? run.askingId
		      })),
		      run.note !== null && React.createElement('p', {
		        key: 'note',
		        role: run.failed ? 'alert' : 'status',
		        style: run.failed ? undefined : { opacity: 0.8 }
		      }, run.note),
		      loadError === undefined && entries.length > 0 && React.createElement('div', {
		        key: 'rows',
		        style: { display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '300px', overflowY: 'auto' }
		      }, entries.map((entry) => React.createElement(TrashRow, {
		        key: entry.sessionId,
		        entry,
		        t: props.t,
		        busy: run.busyId === entry.sessionId,
		        disabled: working,
		        asking: run.askingId === entry.sessionId,
		        onAsk: () => { setRun((previous) => ({ ...previous, askingId: entry.sessionId, askingAll: false })) },
		        onRestore: () => { restore(entry) },
		        onPurge: () => { act({ sessionId: entry.sessionId, label: props.t('trash.purge') }) }
		      })))
		    ]
		  })
		}

		/** One trashed Session: what it was, when it goes, and its two actions. */
		function TrashRow(props   
		                            
		                       
		                        
		                            
		                          
		                            
		                                
		                              
		 )                     {
		  const { entry, t } = props
		  const days = Math.max(0, Math.ceil((entry.expiresAt - Date.now()) / (24 * 60 * 60 * 1000)))
		  return React.createElement('div', {
		    style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', fontSize: '13px' }
		  }, [
		    React.createElement('div', {
		      key: 'what',
		      style: { display: 'flex', flexDirection: 'column', minWidth: 0 }
		    }, [
		      React.createElement('span', {
		        key: 'title',
		        style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
		        title: entry.cwd,
		        children: entry.title ?? entry.cwd
		      }),
		      React.createElement('span', {
		        key: 'meta',
		        style: { opacity: 0.7, fontSize: '12px' },
		        children: [formatBytes(entry.bytes), t('trash.expires', { days })].filter(Boolean).join(' · ')
		      })
		    ]),
		    React.createElement('div', {
		      key: 'actions',
		      style: { display: 'flex', gap: '6px', whiteSpace: 'nowrap' }
		    }, [
		      React.createElement(primitives.Button, {
		        key: 'restore',
		        variant: 'outline',
		        size: 'sm',
		        disabled: props.disabled,
		        onClick: props.onRestore,
		        children: props.busy ? t('trash.working') : t('trash.restore')
		      }),
		      React.createElement(primitives.Button, {
		        key: 'purge',
		        variant: 'outline',
		        // Red at both steps, and always the same red text on the outline: this button
		        // only changes its label when it becomes the confirmation.
		        style: DESTRUCTIVE_TEXT,
		        size: 'sm',
		        disabled: props.disabled,
		        onClick: props.asking ? props.onPurge : props.onAsk,
		        children: props.asking ? t('trash.confirmPurgeButton') : t('trash.purge')
		      })
		    ])
		  ])
		}
		//#endregion
		//#region src/client/index.ts
		/**
		 * Delete-conversation surface, browser half.
		 *
		 * Additive contributions and no takeover:
		 *
		 * - `sidebar.workspaces.session.menu.item` — the red "delete conversation" row
		 *   in one Session's "..." menu.
		 * - `sidebar.footer.action` — the blank-Session cleanup trigger beside Settings, and
		 *   the trash beside it.
		 * - `shell.overlay` — the confirmations and the trash listing those entries open.
		 *
		 * A removal is a MOVE into the trash, so it can be taken back; `POST /api/session.delete`
		 * does the move and the trash routes list, restore and destroy. Every skip decision is
		 * made by `cleanup-plan.ts`. `apply` is also the only place holding the sessions
		 * service, so it hands the dialogs their refresh hop.
		 *
		 * @module @deepseek-ai/dsh-client-ui-session-delete/client
		 */








		/** Required services: the slot registry, the Session list store, and copy. */
		const inject = ['slots', 'sessions', 'locale']

		/**
		 * Re-pull the Host-authoritative Session list after a removal.
		 *
		 * The Host also emits `api-session/removed`, which drops the row without a round
		 * trip; this pull repairs the whole baseline (activity order, the archive set,
		 * the New Session draft) whatever that row was. A failed refresh is not a failed
		 * deletion, so it settles silently.
		 *
		 * @param ctx - the browser root context.
		 * @returns the refresh hop the dialogs call.
		 */
		function sessionRefresh(ctx               )                                        {
		  return async () => {
		    try {
		      await ctx.sessions.refresh()
		    } catch {
		      // The list repaints on the next Host frame anyway.
		    }
		  }
		}

		/**
		 * Register this package's slot entries for the plugin's lifetime.
		 * @param ctx - the browser root context.
		 */
		function apply(ctx               )       {
		  const refreshSessions = sessionRefresh(ctx)

		  ctx.effect(() => ctx.locale.register(LOCALE_NAMESPACE, { zh, en }), 'ui-session-delete: dictionaries')

		  ctx.slots.inject('sidebar.workspaces.session.menu.item', () => ctx.slots.register({
		    name: 'sidebar.workspaces.session.menu.item',
		    id: 'session-delete',
		    order: 900,
		    locale: LOCALE_NAMESPACE
		  }, DeleteSessionMenuItem))

		  ctx.slots.inject('sidebar.footer.action', () => ctx.slots.register({
		    name: 'sidebar.footer.action',
		    id: 'session-cleanup',
		    order: 500,
		    locale: LOCALE_NAMESPACE
		  }, CleanupButton))

		  ctx.slots.inject('shell.overlay', () => ctx.slots.register({
		    name: 'shell.overlay',
		    id: 'session-delete-dialog',
		    locale: LOCALE_NAMESPACE,
		    inject: () => ({ refreshSessions })
		  }, DeleteSessionDialog))

		  ctx.slots.inject('shell.overlay', () => ctx.slots.register({
		    name: 'shell.overlay',
		    id: 'session-cleanup-dialog',
		    locale: LOCALE_NAMESPACE,
		    inject: () => ({ refreshSessions: () => refreshSessions() })
		  }, CleanupDialog))

		  ctx.slots.inject('sidebar.footer.action', () => ctx.slots.register({
		    name: 'sidebar.footer.action',
		    id: 'session-trash',
		    order: 510,
		    locale: LOCALE_NAMESPACE
		  }, TrashButton))

		  ctx.slots.inject('shell.overlay', () => ctx.slots.register({
		    name: 'shell.overlay',
		    id: 'session-trash-dialog',
		    locale: LOCALE_NAMESPACE
		  }, TrashDialog))
		}
		//#endregion
		exports.inject = inject;
		exports.apply = apply;
		return module.exports;
	}
});
