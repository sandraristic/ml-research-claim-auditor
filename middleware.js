
import { timingSafeEqual } from 'node:crypto';
import { next } from '@vercel/functions';

function equalSecrets(left, right) {
  const a = Buffer.from(left, 'utf8');
  const b = Buffer.from(right, 'utf8');

  return a.length === b.length && timingSafeEqual(a, b);
}

function unauthorized() {
  return new Response('Authentication required', {
    status: 401,
    headers: {
      'WWW-Authenticate':
        'Basic realm="ML Research Claim Auditor Demo", charset="UTF-8"',
      'Cache-Control': 'private, no-store',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}

export default function middleware(request) {
  const expectedUser = process.env.DEMO_USERNAME;
  const expectedPassword = process.env.DEMO_PASSWORD;

  // Never expose the app if credentials are missing.
  if (!expectedUser || !expectedPassword) {
    return new Response('Demo access is not configured.', {
      status: 503,
      headers: {
        'Cache-Control': 'private, no-store',
      },
    });
  }

  const auth = request.headers.get('authorization') ?? '';
  const match = /^Basic\s+([A-Za-z0-9+/=]+)$/i.exec(auth);

  if (!match) return unauthorized();

  let decoded;

  try {
    decoded = Buffer.from(match[1], 'base64').toString('utf8');
  } catch {
    return unauthorized();
  }

  const delimiter = decoded.indexOf(':');

  if (delimiter < 0) return unauthorized();

  const user = decoded.slice(0, delimiter);
  const password = decoded.slice(delimiter + 1);

  if (
    !equalSecrets(user, expectedUser) ||
    !equalSecrets(password, expectedPassword)
  ) {
    return unauthorized();
  }

  return next();
}

export const config = {
  runtime: 'nodejs',
  matcher: '/:path*',
};
