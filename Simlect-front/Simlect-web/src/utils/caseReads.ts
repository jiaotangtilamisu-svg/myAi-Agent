/** Coalesce only simultaneous reads for the same user. No result cache or token storage. */
const pending = new Map<string, Promise<unknown>>();
export function readCasesOnce<T>(userId: string, read: () => Promise<T>): Promise<T> {
  if (!userId) return read();
  const current = pending.get(userId);
  if (current) return current as Promise<T>;
  const task = Promise.resolve().then(read).finally(() => {
    if (pending.get(userId) === task) pending.delete(userId);
  });
  pending.set(userId, task);
  return task;
}
