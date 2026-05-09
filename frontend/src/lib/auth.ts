import type { NextAuthOptions } from 'next-auth';
import type { Adapter } from 'next-auth/adapters';
import CredentialsProvider from 'next-auth/providers/credentials';
import { PrismaAdapter } from '@auth/prisma-adapter';
import bcrypt from 'bcryptjs';
import { prisma } from '@/lib/prisma';

export const authOptions: NextAuthOptions = {
  // The adapter persists accounts and verification tokens to MongoDB.
  // With JWT strategy it does NOT write session records to the DB.
  // Cast required: @auth/prisma-adapter v2 ships @auth/core types which are
  // structurally identical to next-auth v4's Adapter but TS treats them as
  // different due to separate type roots.
  adapter: PrismaAdapter(prisma) as Adapter,

  session: {
    strategy: 'jwt',
    // Expire sessions after 30 days of inactivity.
    maxAge: 30 * 24 * 60 * 60,
  },

  providers: [
    CredentialsProvider({
      name: 'credentials',
      credentials: {
        email: { label: 'Email', type: 'email', placeholder: 'you@example.com' },
        password: { label: 'Password', type: 'password' },
      },

      async authorize(credentials) {
        // ── Input validation ─────────────────────────────────────────────
        if (!credentials?.email || !credentials.password) {
          throw new Error('Email and password are required.');
        }

        // ── User lookup ──────────────────────────────────────────────────
        const user = await prisma.user.findUnique({
          where: { email: credentials.email.toLowerCase().trim() },
          select: {
            id: true,
            name: true,
            email: true,
            image: true,
            password: true,
            role: true,
          },
        });

        if (!user || !user.password) {
          // Return null — NextAuth converts this to a generic auth error.
          // Do NOT expose whether the email or password was wrong.
          return null;
        }

        // ── Password verification ────────────────────────────────────────
        const passwordValid = await bcrypt.compare(
          credentials.password,
          user.password,
        );

        if (!passwordValid) {
          return null;
        }

        // Return the subset of user data to be encoded in the JWT.
        return {
          id: user.id,
          name: user.name,
          email: user.email,
          image: user.image,
          role: user.role,
        };
      },
    }),
  ],

  callbacks: {
    /**
     * jwt — runs when the JWT is created (sign-in) or refreshed.
     * Embed `id` and `role` so the session callback can expose them.
     */
    async jwt({ token, user }) {
      if (user) {
        // `user` is only populated on the initial sign-in.
        token.id = user.id;
        token.role = user.role;
      }
      return token;
    },

    /**
     * session — shapes the `session` object available to the client via
     * `useSession()` / `getServerSession()`.
     */
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.id;
        session.user.role = token.role;
      }
      return session;
    },
  },

  pages: {
    // Redirect to our custom login page instead of NextAuth's built-in one.
    signIn: '/login',
    error: '/login',
  },

  // Must be set via NEXTAUTH_SECRET environment variable in production.
  secret: process.env.NEXTAUTH_SECRET,

  debug: process.env.NODE_ENV === 'development',
};
