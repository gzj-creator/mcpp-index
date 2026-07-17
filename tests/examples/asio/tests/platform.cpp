#include <asio.hpp>

#include <array>
#include <string>

int main() {
#if defined(ASIO_HAS_PIPE)
    asio::io_context io;
    asio::readable_pipe reader(io);
    asio::writable_pipe writer(io);
    asio::error_code ec;
    asio::connect_pipe(reader, writer, ec);
    if (ec) return 1;

    const std::string sent = "pipe";
    std::array<char, 4> received{};
    if (asio::write(writer, asio::buffer(sent), ec) != sent.size() || ec) return 2;
    if (asio::read(reader, asio::buffer(received), ec) != sent.size() || ec) return 3;
    if (std::string(received.data(), received.size()) != sent) return 4;
#endif

#if defined(ASIO_HAS_LOCAL_SOCKETS)
    static_assert(sizeof(asio::local::stream_protocol::endpoint) > 0);
#endif
#if defined(ASIO_HAS_POSIX_STREAM_DESCRIPTOR)
    static_assert(sizeof(asio::posix::stream_descriptor::native_handle_type) > 0);
#endif
#if defined(ASIO_HAS_WINDOWS_STREAM_HANDLE)
    static_assert(sizeof(asio::windows::stream_handle::native_handle_type) > 0);
#endif
#if defined(ASIO_HAS_WINDOWS_OBJECT_HANDLE)
    static_assert(sizeof(asio::windows::object_handle::native_handle_type) > 0);
#endif
#if defined(ASIO_HAS_FILE)
    static_assert(sizeof(asio::random_access_file::native_handle_type) > 0);
#endif
#if defined(ASIO_HAS_SERIAL_PORT)
    static_assert(sizeof(asio::serial_port::native_handle_type) > 0);
#endif

    return 0;
}
