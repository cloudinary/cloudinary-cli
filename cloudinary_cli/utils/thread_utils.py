from multiprocessing import pool


def run_tasks_concurrently(func, tasks, concurrent_workers):
    thread_pool = pool.ThreadPool(concurrent_workers)
    thread_pool.starmap(func, tasks)
