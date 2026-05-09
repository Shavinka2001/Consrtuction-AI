// Prisma CLI configuration for Construction AI.
// MongoDB does NOT support prisma migrate — use `npx prisma db push` instead.
import "dotenv/config";
import { defineConfig } from "prisma/config";

export default defineConfig({
  schema: "prisma/schema.prisma",
  // Provides the connection URL to the Prisma CLI (db push, studio, etc.).
  datasource: {
    url: process.env["DATABASE_URL"],
  },
});
