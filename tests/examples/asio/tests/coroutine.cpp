#include <asio.hpp>

#include <chrono>

#ifndef ASIO_HAS_CO_AWAIT
#error "C++23 compat.asio consumers must have co_await support"
#endif
#ifndef ASIO_HAS_STD_COROUTINE
#error "C++23 compat.asio consumers must use the standard coroutine library"
#endif

asio::awaitable<int> timer_value() {
    asio::steady_timer timer(co_await asio::this_coro::executor);
    timer.expires_after(std::chrono::milliseconds(1));
    co_await timer.async_wait(asio::use_awaitable);
    co_return 42;
}

int main() {
    asio::io_context io;
    int result = 0;
    bool completed = false;

    asio::co_spawn(io, timer_value(),
        [&](std::exception_ptr error, int value) {
            if (!error) {
                result = value;
                completed = true;
            }
        });

    io.run();
    return completed && result == 42 ? 0 : 1;
}
