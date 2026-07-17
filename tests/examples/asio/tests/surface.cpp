#include <asio.hpp>
#include <asio/execution_context.hpp>
#include <asio/experimental/as_single.hpp>
#include <asio/experimental/awaitable_operators.hpp>
#include <asio/experimental/basic_channel.hpp>
#include <asio/experimental/basic_concurrent_channel.hpp>
#include <asio/experimental/cancellation_condition.hpp>
#include <asio/experimental/channel.hpp>
#include <asio/experimental/channel_error.hpp>
#include <asio/experimental/channel_traits.hpp>
#include <asio/experimental/co_composed.hpp>
#include <asio/experimental/co_spawn.hpp>
#include <asio/experimental/concurrent_channel.hpp>
#include <asio/experimental/coro.hpp>
#include <asio/experimental/coro_traits.hpp>
#include <asio/experimental/parallel_group.hpp>
#include <asio/experimental/promise.hpp>
#include <asio/experimental/use_coro.hpp>
#include <asio/experimental/use_promise.hpp>
#include <asio/yield.hpp>
#include <asio/unyield.hpp>

#ifndef ASIO_STANDALONE
#error "compat.asio must expose standalone Asio to consumers"
#endif
#ifndef ASIO_HEADER_ONLY
#error "compat.asio must expose Asio's header-only configuration"
#endif
#ifndef ASIO_DISABLE_BOOST_CONTEXT_FIBER
#error "compat.asio must make the excluded Boost.Context spawn path explicit"
#endif
#ifdef ASIO_ENABLE_BOOST
#error "compat.asio must not enable Boost.Asio mode"
#endif
#ifdef ASIO_HAS_BOOST_CONFIG
#error "standalone Asio must not depend on Boost.Config"
#endif
#ifdef ASIO_HAS_BOOST_REGEX
#error "standalone Asio must not expose Boost.Regex overloads"
#endif
#ifdef ASIO_HAS_BOOST_DATE_TIME
#error "standalone Asio must not expose legacy Boost.Date_Time timers"
#endif
#ifdef ASIO_HAS_IO_URING
#error "compat.asio base package must not require liburing"
#endif

#include <type_traits>

int main() {
    static_assert(std::is_class_v<asio::io_context>);
    static_assert(std::is_class_v<asio::thread_pool>);
    static_assert(std::is_class_v<asio::steady_timer>);
    static_assert(std::is_class_v<asio::ip::tcp::socket>);
    static_assert(std::is_class_v<asio::ip::udp::socket>);
    static_assert(std::is_class_v<asio::ip::icmp::socket>);
    static_assert(std::is_class_v<asio::experimental::channel<void(asio::error_code, int)>>);
    static_assert(std::is_class_v<asio::experimental::concurrent_channel<void(asio::error_code, int)>>);

#if defined(ASIO_HAS_POSIX_STREAM_DESCRIPTOR)
    static_assert(std::is_class_v<asio::posix::stream_descriptor>);
#endif
#if defined(ASIO_HAS_LOCAL_SOCKETS)
    static_assert(std::is_class_v<asio::local::stream_protocol::socket>);
#endif
#if defined(ASIO_HAS_PIPE)
    static_assert(std::is_class_v<asio::readable_pipe>);
    static_assert(std::is_class_v<asio::writable_pipe>);
#endif
#if defined(ASIO_HAS_SERIAL_PORT)
    static_assert(std::is_class_v<asio::serial_port>);
#endif
#if defined(ASIO_HAS_WINDOWS_STREAM_HANDLE)
    static_assert(std::is_class_v<asio::windows::stream_handle>);
#endif
#if defined(ASIO_HAS_WINDOWS_OBJECT_HANDLE)
    static_assert(std::is_class_v<asio::windows::object_handle>);
#endif
#if defined(ASIO_HAS_FILE)
    static_assert(std::is_class_v<asio::random_access_file>);
#endif

    return 0;
}
