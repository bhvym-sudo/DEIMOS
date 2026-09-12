package main

import (
	"log"
	"net/http"

	"deimos/internal/server"
)

func main() {
	root, err := server.RootFromWorkingDirectory()
	if err != nil {
		log.Fatal(err)
	}
	service, err := server.New(root)
	if err != nil {
		log.Fatal(err)
	}
	defer service.Close()
	service.StartEngines()
	service.StartHeartbeat()
	address := server.ListenAddress()
	log.Println(server.Banner(address))
	log.Fatal(http.ListenAndServe(address, service.Handler()))
}
