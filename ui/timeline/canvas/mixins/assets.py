class AssetsMixin:
    def _cleanup_threads(self):
        """Clears pending thumbnail loads to prevent crashes on exit."""
        self.thread_pool.clear()
