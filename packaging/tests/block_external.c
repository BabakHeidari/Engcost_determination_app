/* Native Linux fixture testing only; never part of the customer application. */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <netdb.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>

int connect(int fd, const struct sockaddr *address, socklen_t length) {
    if (address && address->sa_family == AF_INET) {
        const struct sockaddr_in *a = (const struct sockaddr_in *)address;
        if ((ntohl(a->sin_addr.s_addr) >> 24) != 127) { errno = ENETUNREACH; return -1; }
    } else if (address && address->sa_family == AF_INET6) {
        const struct sockaddr_in6 *a = (const struct sockaddr_in6 *)address;
        if (!IN6_IS_ADDR_LOOPBACK(&a->sin6_addr)) { errno = ENETUNREACH; return -1; }
    }
    int (*original)(int,const struct sockaddr*,socklen_t) = dlsym(RTLD_NEXT,"connect");
    return original(fd,address,length);
}

int getaddrinfo(const char *name, const char *service, const struct addrinfo *hints, struct addrinfo **result) {
    if (name && strcmp(name,"127.0.0.1") && strcmp(name,"localhost") && strcmp(name,"::1")) return EAI_FAIL;
    int (*original)(const char*,const char*,const struct addrinfo*,struct addrinfo**) = dlsym(RTLD_NEXT,"getaddrinfo");
    return original(name,service,hints,result);
}
