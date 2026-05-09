import { PrismaClient } from '@/generated/prisma/client';

// Prevent multiple PrismaClient instances in development (Next.js hot-reload
// re-evaluates modules, which would otherwise open new DB connections).
declare global {
  // eslint-disable-next-line no-var
  var prisma: PrismaClient | undefined;
}

export const prisma: PrismaClient =
  globalThis.prisma ??
  new PrismaClient({
    // The schema has no `url` in the datasource block (Prisma v7 requirement),
    // so we pass the connection string to the constructor at runtime.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ...(process.env.DATABASE_URL ? ({ datasourceUrl: process.env.DATABASE_URL } as any) : {}),
    log:
      process.env.NODE_ENV === 'development'
        ? ['query', 'warn', 'error']
        : ['error'],
  });

if (process.env.NODE_ENV !== 'production') {
  globalThis.prisma = prisma;
}
