#include <asio.hpp>
#include <asio/experimental/awaitable_operators.hpp>
#include <asio/experimental/channel.hpp>
#include <asio/experimental/concurrent_channel.hpp>
#include <asio/experimental/parallel_group.hpp>
#include <asio/experimental/promise.hpp>
#include <asio/experimental/use_promise.hpp>

#include <string>
#include <utility>

int main() {
    asio::io_context io;

    asio::experimental::channel<void(asio::error_code, std::string)> channel(io, 1);
    if (!channel.try_send(asio::error_code{}, "channel")) return 1;
    std::string channel_value;
    asio::error_code channel_error;
    channel.async_receive([&](asio::error_code ec, std::string value) {
        channel_error = ec;
        channel_value = std::move(value);
    });

    asio::experimental::concurrent_channel<void(asio::error_code, int)> concurrent(io, 1);
    if (!concurrent.try_send(asio::error_code{}, 42)) return 2;
    int concurrent_value = 0;
    asio::error_code concurrent_error;
    concurrent.async_receive([&](asio::error_code ec, int value) {
        concurrent_error = ec;
        concurrent_value = value;
    });

    auto promised = asio::post(io, asio::experimental::use_promise);
    bool promise_completed = false;
    promised([&] { promise_completed = true; });

    io.run();

    return !channel_error && channel_value == "channel"
        && !concurrent_error && concurrent_value == 42
        && promise_completed ? 0 : 3;
}
