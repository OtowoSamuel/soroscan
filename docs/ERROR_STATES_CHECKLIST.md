# Issue #618: Error States & Validation Messages - Implementation Checklist

**Status**: Not Started  
**Estimated Completion**: 1 day  
**Owner**: [Assign team member]

**Philosophy**: Document patterns once, reuse everywhere. No separate component library needed—use Tailwind + existing UI components.

---

## MVP Deliverables

### 1. Error Patterns Documentation
- [ ] Create `docs/ERROR_PATTERNS.md` (developer guide, 3-4 pages max)
- [ ] Document when to use each pattern:
  - [ ] **Inline validation**: form field errors (email invalid, required, etc.)
  - [ ] **Toast notification**: transient feedback (success, error, info)
  - [ ] **Error banner**: persistent alerts (network offline, feature disabled)
  - [ ] **Error page**: full-screen error (404, 500, permission denied)
- [ ] Provide code snippets for each pattern
- [ ] Include color references: red-500 (danger), orange-500 (warning), blue-500 (info), green-500 (success)

**Content Outline**:
```markdown
# Error State Patterns

## 1. Inline Form Validation
- When: user submits invalid form or focuses away from field
- Visual: red border + red error text below input
- Accessibility: error text associated with input via aria-describedby
- Example: "Email must be valid"

## 2. Toast Notifications
- When: action completes (success/error) or async operation updates
- Visual: small box, bottom-right, auto-dismiss after 3-5s
- Duration: success 3s, error 5s, info 4s
- Color: green (success), red (error), blue (info)
- Accessibility: aria-live="polite"

## 3. Error Banners
- When: persistent issue (network offline, API unavailable)
- Visual: banner at top of page, full width, dismissible
- Color: background red-50 / red-100 (dark), text red-900
- Icon: alert triangle or exclamation mark
- Action: retry button (optional)

## 4. Error Pages (404, 500, 403)
- When: user navigates to non-existent page or server error
- Visual: large error code, friendly message, helpful links
- Content: error explanation, link to homepage, search option (if applicable)
- No: don't show technical stack traces to users

## 5. Loading States
- When: data fetching or processing
- Option A: skeleton screen (gray placeholder matching content shape)
- Option B: spinner (spinning animation)
- When to use: skeleton for content-heavy (tables, lists), spinner for dialogs/actions
- Text: optional "Loading..." message

## 6. Success States
- When: action completes successfully
- Visual: green checkmark icon, brief success message
- Animation: fade-in, optional scale animation (subtle)
- Dismissal: auto-hide after 3s or on next action

## 7. Validation States (form)
- Empty: gray border, placeholder text
- Valid: green checkmark icon to right of input
- Invalid: red border, red error text below, clear message
- Loading: spinner inside or to right of input
```

### 2. Error Pages (404, 500, 403)
Create in both apps:

#### Admin App
- [ ] Create `admin/app/not-found.tsx` (404)
- [ ] Create `admin/app/error.tsx` (500 / server error)
- [ ] Create `admin/app/forbidden.tsx` (403) optional

#### Frontend App
- [ ] Create `soroscan-frontend/app/not-found.tsx` (404)
- [ ] Create `soroscan-frontend/app/error.tsx` (500)

**404 Page Template**:
```typescript
// app/not-found.tsx
export default function NotFoundPage() {
  return (
    <div className="flex h-screen items-center justify-center bg-zinc-950">
      <div className="text-center">
        <h1 className="text-6xl font-bold text-zinc-100">404</h1>
        <p className="mt-4 text-xl text-zinc-400">Page not found</p>
        <p className="mt-2 text-zinc-500">The page you're looking for doesn't exist.</p>
        <div className="mt-8 flex justify-center gap-4">
          <a href="/" className="rounded bg-blue-600 px-6 py-2 text-white hover:bg-blue-700">
            Go Home
          </a>
          <a href="/search" className="rounded bg-zinc-800 px-6 py-2 text-white hover:bg-zinc-700">
            Search
          </a>
        </div>
      </div>
    </div>
  );
}
```

**500 Page Template**:
```typescript
// app/error.tsx
'use client';

export default function ErrorPage({ error, reset }) {
  return (
    <div className="flex h-screen items-center justify-center bg-zinc-950">
      <div className="text-center">
        <h1 className="text-6xl font-bold text-zinc-100">500</h1>
        <p className="mt-4 text-xl text-zinc-400">Server error</p>
        <p className="mt-2 text-zinc-500">{error?.message || 'Something went wrong'}</p>
        <div className="mt-8 flex justify-center gap-4">
          <button onClick={() => reset()} className="rounded bg-blue-600 px-6 py-2 text-white hover:bg-blue-700">
            Try Again
          </button>
          <a href="/" className="rounded bg-zinc-800 px-6 py-2 text-white hover:bg-zinc-700">
            Go Home
          </a>
        </div>
      </div>
    </div>
  );
}
```

### 3. Toast Notification Component
- [ ] Check if toast component exists: `components/ui/Toast.tsx` or `components/notifications/Toast.tsx`
- [ ] If not, create simple toast provider using React Context
- [ ] Toast interface:
  ```typescript
  type Toast = {
    id: string;
    type: 'success' | 'error' | 'info' | 'warning';
    message: string;
    duration?: number; // ms, default 3000
  };
  ```
- [ ] Usage:
  ```typescript
  const { addToast } = useToast();
  addToast({ type: 'success', message: 'Webhook created!' });
  ```

### 4. Form Validation Pattern
- [ ] Document form validation flow
- [ ] Using React Hook Form (if available, check package.json):
  ```typescript
  <input 
    {...register('email', { required: 'Email required' })}
    aria-describedby={errors.email ? 'email-error' : undefined}
  />
  {errors.email && (
    <p id="email-error" className="mt-1 text-sm text-red-500">
      {errors.email.message}
    </p>
  )}
  ```

### 5. Network Error Handling
- [ ] Create `utils/networkDetection.ts`:
  - [ ] Listen to `navigator.onLine` or fetch retry logic
  - [ ] Show banner when offline
  - [ ] Hide banner when back online
- [ ] Banner component:
  ```typescript
  function OfflineBanner() {
    const [isOnline, setIsOnline] = useState(true);
    
    useEffect(() => {
      const handleOnline = () => setIsOnline(true);
      const handleOffline = () => setIsOnline(false);
      
      window.addEventListener('online', handleOnline);
      window.addEventListener('offline', handleOffline);
      
      return () => {
        window.removeEventListener('online', handleOnline);
        window.removeEventListener('offline', handleOffline);
      };
    }, []);
    
    if (isOnline) return null;
    
    return (
      <div className="bg-red-900 text-white p-3 text-center">
        You're offline. Some features may not work.
      </div>
    );
  }
  ```

### 6. Rate Limit (429) Handling
- [ ] Detect 429 responses in GraphQL client
- [ ] Show banner with countdown timer:
  ```typescript
  function RateLimitBanner({ resetAt }) {
    const [countdown, setCountdown] = useState(0);
    
    useEffect(() => {
      const interval = setInterval(() => {
        const remaining = Math.ceil((resetAt - Date.now()) / 1000);
        setCountdown(Math.max(0, remaining));
      }, 1000);
      
      return () => clearInterval(interval);
    }, [resetAt]);
    
    if (countdown === 0) return null;
    
    return (
      <div className="bg-amber-900 text-white p-3 text-center">
        Rate limited. Try again in {countdown}s
      </div>
    );
  }
  ```

### 7. Accessibility Annotations
- [ ] All error messages: use `aria-describedby` to connect to input
- [ ] Toast notifications: use `aria-live="polite"` + `role="status"`
- [ ] Error icons: use `aria-label="error"` or wrap in `<span aria-hidden="true">`
- [ ] Form labels: always use `<label htmlFor="inputId">`
- [ ] Keyboard navigation: Tab through form, focus visible, Enter to submit

---

## Files to Create/Modify

```
docs/
└── ERROR_PATTERNS.md 📝 NEW (3-4 pages, guide for devs)

admin/app/
├── not-found.tsx 📝 NEW
├── error.tsx 📝 NEW
└── forbidden.tsx 📝 NEW (optional)

soroscan-frontend/app/
├── not-found.tsx 📝 NEW
├── error.tsx 📝 NEW
└── [utils/]
    └── networkDetection.ts 📝 NEW (if needed)

soroscan-frontend/components/
└── [ui/ or notifications/]
    └── Toast.tsx 📝 NEW (if not exists)

soroscan-frontend/context/
└── ToastContext.tsx 📝 NEW (if creating toast provider)
```

---

## Acceptance Tests

### Documentation
- [ ] ERROR_PATTERNS.md is clear and concise (devs understand patterns)
- [ ] Code examples are copy-paste ready
- [ ] Color palette documented (red-500 for danger, etc.)

### Error Pages
- [ ] 404 page loads without errors
- [ ] 500 page handles missing error message gracefully
- [ ] Both pages styled consistently with app theme
- [ ] Mobile: text readable, buttons touchable (44px+)
- [ ] Dark mode: readable

### Toast Component
- [ ] Toast appears/disappears correctly
- [ ] Multiple toasts stack (show 2-3 at once)
- [ ] Auto-dismiss after 3-5s
- [ ] Dismiss button works
- [ ] Keyboard accessible (focus visible)

### Form Validation
- [ ] Invalid input shows error message
- [ ] Valid input hides error message
- [ ] Accessible: screen reader reads error
- [ ] Red border clearly visible

### Network/Rate Limit
- [ ] Offline banner appears when disconnected
- [ ] Rate limit countdown shows and counts down
- [ ] Banners dismissible (optional)

---

## Fastest Approach for MVP

1. **2 hours**: Write ERROR_PATTERNS.md + code snippets
2. **1 hour**: Create 404/500 pages (copy template)
3. **30 min**: Add Toast component (use existing if available, else simple context)
4. **30 min**: Test + dark mode checks

**Total**: 1 day

---

## Questions

- [ ] Does project already have a toast/notification system?
- [ ] Which GraphQL client is used? (Apollo, graphql-request, urql?)
- [ ] Do we need rate limit error handling, or is that backend's job?
- [ ] Should error pages have illustrations/images, or keep simple?

---

## References

- Tailwind colors: https://tailwindcss.com/docs/customizing-colors
- ARIA accessibility: https://www.w3.org/WAI/tutorials/
- React error boundaries: https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary
- Network API: https://developer.mozilla.org/en-US/docs/Web/API/Navigator/onLine
