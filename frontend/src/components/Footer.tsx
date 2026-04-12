export default function Footer() {
  return (
    <footer className="border-t border-border mt-20">
      <div className="mx-auto max-w-7xl px-4 py-8 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-muted">
        <p>
          &copy; {new Date().getFullYear()} Catandary. All rights reserved.
        </p>
        <div className="flex items-center gap-4">
          <span>
            Powered by{" "}
            <a
              href="https://catandary.de"
              className="text-accent hover:underline"
            >
              Catandary Foresight
            </a>
          </span>
        </div>
      </div>
    </footer>
  );
}
