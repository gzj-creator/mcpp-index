#include <asio.hpp>

#include <atomic>
#include <chrono>
#include <mutex>
#include <vector>

#if !defined(_WIN32)
#ifndef ASIO_HAS_THREADS
#error "Asio must detect POSIX thread support"
#endif
#ifndef ASIO_HAS_PTHREADS
#error "Asio must select its pthread implementation on POSIX"
#endif
#endif

int main() {
    using namespace std::chrono_literals;

    asio::io_context io;
    auto guard = asio::make_work_guard(io);
    auto serial = asio::make_strand(io);
    asio::steady_timer timer(io, 2ms);

    std::atomic<int> posted{0};
    std::mutex order_mutex;
    std::vector<int> order;
    bool timer_called = false;

    asio::post(serial, [&] {
        std::lock_guard lock(order_mutex);
        order.push_back(1);
        ++posted;
    });
    asio::post(serial, [&] {
        std::lock_guard lock(order_mutex);
        order.push_back(2);
        ++posted;
    });
    timer.async_wait([&](const asio::error_code& ec) {
        timer_called = !ec;
        guard.reset();
    });

    asio::thread worker([&] { io.run(); });
    worker.join();

    if (posted != 2 || !timer_called || order != std::vector<int>{1, 2}) return 1;

    asio::thread_pool pool(2);
    std::atomic<int> pooled{0};
    asio::post(pool, [&] { ++pooled; });
    asio::post(pool, [&] { ++pooled; });
    pool.join();
    if (pooled != 2) return 2;

    asio::io_context cancel_io;
    asio::steady_timer cancelled(cancel_io, 1h);
    asio::cancellation_signal cancellation;
    asio::error_code cancelled_ec;
    bool cancelled_called = false;
    cancelled.async_wait(asio::bind_cancellation_slot(
        cancellation.slot(),
        [&](const asio::error_code& ec) {
            cancelled_ec = ec;
            cancelled_called = true;
        }));
    cancellation.emit(asio::cancellation_type::all);
    cancel_io.run();

    return cancelled_called && cancelled_ec == asio::error::operation_aborted ? 0 : 3;
}
